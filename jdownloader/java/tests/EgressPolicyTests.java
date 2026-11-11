// SPDX-License-Identifier: GPL-3.0-or-later
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.Proxy;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * PC tests for egress policy omni-public-only-v1 (audit JD-03). Run with the user's own JDownloader jars on the
 * classpath (never shipped), our compiled classes and META-INF/services, and:
 *   -Dsun.net.inetaddr.ttl=0  -Dsun.net.inetaddr.negative.ttl=0  (fake DNS answers come from a test upstream)
 * Modes (one per JVM, because the layers are JVM-wide):
 *   unit       address rules, no network
 *   prod       production install(): resolver, guard, sockets, JD socket factory, DNS rebind flip, LAN targets
 *   redirect   install() with one loopback alias (127.0.0.7) treated as public: a "public" page 302s to a
 *              private one, through java.net.URL and through JDownloader's own HTTP stack
 *   online     production install(): public HTTPS and HTTP sites work through every layer
 */
public final class EgressPolicyTests {
    static int passed, failed;
    static final List<String> failures = new ArrayList<>();

    static void check(String name, boolean ok, String detail) {
        if (ok) { passed++; System.out.println("PASS " + name); }
        else { failed++; failures.add(name); System.out.println("FAIL " + name + (detail == null ? "" : " :: " + detail)); }
    }

    static InetAddress ip(String text) throws Exception { return InetAddress.getByName(text); }   // literals only

    // A tiny HTTP server that counts every request it receives.
    static final class Server implements AutoCloseable {
        final ServerSocket socket;
        final AtomicInteger hits = new AtomicInteger();
        final String location;
        Server(String bind, String location) throws IOException {
            this.location = location;
            socket = new ServerSocket();
            socket.bind(new InetSocketAddress(InetAddress.getByName(bind), 0), 16);
            Thread t = new Thread(this::run, "test-server-" + bind);
            t.setDaemon(true);
            t.start();
        }
        int port() { return socket.getLocalPort(); }
        void run() {
            while (!socket.isClosed()) {
                try (Socket c = socket.accept()) {
                    c.setSoTimeout(5000);
                    InputStream in = c.getInputStream();
                    ByteArrayOutputStream head = new ByteArrayOutputStream();
                    int prev = 0, b;
                    while ((b = in.read()) >= 0) { head.write(b); String h = head.toString("ISO-8859-1"); if (h.endsWith("\r\n\r\n")) break; }
                    hits.incrementAndGet();
                    String reply = location != null
                        ? "HTTP/1.1 302 Found\r\nLocation: " + location + "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                        : "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 6\r\nConnection: close\r\n\r\nsecret";
                    c.getOutputStream().write(reply.getBytes(StandardCharsets.ISO_8859_1));
                } catch (IOException ignored) { }
            }
        }
        public void close() throws IOException { socket.close(); }
    }

    /** Sends one raw request to the guard; returns the status line. */
    static String viaGuard(OmniEgressPolicy p, String request) throws IOException {
        try (Socket s = new Socket(Proxy.NO_PROXY)) {
            s.connect(new InetSocketAddress("127.0.0.1", p.port()), 5000);
            s.setSoTimeout(20000);
            s.getOutputStream().write(request.getBytes(StandardCharsets.ISO_8859_1));
            InputStream in = s.getInputStream();
            ByteArrayOutputStream line = new ByteArrayOutputStream();
            int b;
            while ((b = in.read()) >= 0 && b != '\n') line.write(b);
            return line.toString("ISO-8859-1").trim();
        }
    }

    static String connect(OmniEgressPolicy p, String target) throws IOException {
        return viaGuard(p, "CONNECT " + target + " HTTP/1.1\r\nHost: " + target + "\r\n\r\n");
    }

    static String get(OmniEgressPolicy p, String url) throws IOException {
        return viaGuard(p, "GET " + url + " HTTP/1.1\r\nHost: x\r\n\r\n");
    }

    static String lanAddress() throws Exception {
        for (NetworkInterface nif : Collections.list(NetworkInterface.getNetworkInterfaces())) {
            if (!nif.isUp() || nif.isLoopback()) continue;
            for (InetAddress a : Collections.list(nif.getInetAddresses())) {
                if (a.getAddress().length == 4 && !a.isLinkLocalAddress()) return a.getHostAddress();
            }
        }
        return null;
    }

    static List<String> allInterfaceAddresses() throws Exception {
        List<String> out = new ArrayList<>();
        for (NetworkInterface nif : Collections.list(NetworkInterface.getNetworkInterfaces()))
            for (InetAddress a : Collections.list(nif.getInetAddresses())) out.add(a.getHostAddress().split("%")[0]);
        return out;
    }

    // ------------------------------------------------------------------------------------------
    static void unit() throws Exception {
        String[] refused = {"127.0.0.1", "127.255.255.254", "10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.1.1",
            "169.254.169.254", "100.64.0.1", "100.127.255.254", "0.0.0.0", "0.1.2.3", "224.0.0.1", "239.255.255.250",
            "255.255.255.255", "240.0.0.1", "192.0.0.8", "192.0.2.1", "198.18.0.1", "198.51.100.7", "203.0.113.9",
            "::", "::1", "fe80::1", "fc00::1", "fd12:3456::1", "fec0::1", "ff02::1", "::ffff:127.0.0.1",
            "::ffff:192.168.1.1", "::ffff:10.1.2.3", "::127.0.0.1", "64:ff9b::a00:1", "2001:db8::1", "2001::1",
            "2002:c0a8:101::1", "3fff::1", "100::1"};
        for (String r : refused) check("refuse " + r, !OmniPublicAddress.isPublic(ip(r)), null);
        String[] allowedList = {"8.8.8.8", "1.1.1.1", "93.184.215.14", "172.15.255.255", "172.32.0.1", "100.63.255.255",
            "100.128.0.1", "192.169.0.1", "2606:4700:4700::1111", "2a00:1450:4001::1", "::ffff:8.8.4.4"};
        for (String a : allowedList) check("allow " + a, OmniPublicAddress.isPublic(ip(a)), null);
        for (String own : allInterfaceAddresses()) check("refuse own interface " + own, !OmniPublicAddress.isPublic(ip(own)), null);
        check("console subnets read", OmniPublicAddress.consoleSubnets() > 0, String.valueOf(OmniPublicAddress.consoleSubnets()));
        check("literal ipv4", OmniPublicAddress.literal("10.0.0.1") != null, null);
        check("literal ipv6 bracket", OmniPublicAddress.literal("[::1]") != null, null);
        check("not literal name", OmniPublicAddress.literal("example.com") == null, null);
        check("not literal hex-name", OmniPublicAddress.literal("deadbeef:foo") == null, null);
        for (String n : new String[]{"2130706433", "0x7f000001", "0x7f.1", "127.1", "017700000001", "10.1"})
            check("numeric-looking " + n, OmniPublicAddress.numericLooking(n), null);
        for (String n : new String[]{"example.com", "1.example.com", "a1b2", "x0x7f"})
            check("name " + n, !OmniPublicAddress.numericLooking(n), null);
    }

    // ------------------------------------------------------------------------------------------
    static void prod() throws Exception {
        try (Server secret = new Server("127.0.0.1", null)) {
            int sp = secret.port();
            OmniEgressPolicy p = OmniEgressPolicy.install();
            check("install proves every layer", p != null, null);
            check("resolver provider installed", OmniPublicResolverProvider.installed(), null);
            check("localhost answers loopback", InetAddress.getByName("localhost").isLoopbackAddress(), null);
            check("own host name answers loopback", InetAddress.getLocalHost().isLoopbackAddress(), InetAddress.getLocalHost().toString());

            // Resolver: names with private answers fail JVM-wide (a fake upstream stands in for DNS).
            String[][] names = {{"rebind.test", "private answer"}, {"lan6.test", "IPv6 ULA answer"}, {"mixed.test", "one private answer among public"},
                                {"loop.test", "loopback answer"}, {"cgnat.test", "CGNAT answer"}, {"meta.test", "link-local metadata answer"},
                                {"mapped.test", "IPv4-mapped private answer"}};
            for (String[] n : names) {
                try { InetAddress.getAllByName(n[0]); check("resolver refuses " + n[0] + " (" + n[1] + ")", false, "resolved"); }
                catch (java.net.UnknownHostException e) { check("resolver refuses " + n[0] + " (" + n[1] + ")", e.getMessage().startsWith(OmniPublicAddress.POLICY), e.getMessage()); }
            }
            check("resolver allows public answer", InetAddress.getAllByName("public.test").length == 1, null);
            for (String n : new String[]{"2130706433", "0x7f.1", "017700000001"}) {
                boolean refusedIt;
                try { InetAddress.getAllByName(n); refusedIt = false; } catch (java.net.UnknownHostException | IllegalArgumentException e) { refusedIt = true; }
                boolean usable = false;
                if (!refusedIt) { try { usable = OmniPublicAddress.isPublic(InetAddress.getAllByName(n)[0]); } catch (Exception e) { usable = false; } }
                // Java itself reads some of these as address literals (2130706433 is 127.0.0.1): never a public answer.
                check("numeric-looking name never yields a public address: " + n, refusedIt || !usable, null);
            }
            check("resolver refuses .invalid without DNS", refusedByResolver("anything.invalid"), null);

            // Guard: every private form is 403, the secret server is never contacted.
            String[] targets = {"127.0.0.1:" + sp, "localhost:" + sp, "[::1]:" + sp, "[::ffff:127.0.0.1]:" + sp,
                "2130706433:" + sp, "0x7f000001:" + sp, "0x7f.1:" + sp, "127.1:" + sp, "rebind.test:" + sp, "loop.test:" + sp,
                "mixed.test:443", "lan6.test:443", "10.0.0.1:80", "192.168.1.1:80", "169.254.169.254:80", "100.64.0.1:80",
                "0.0.0.0:" + sp, "[fe80::1]:80", "[fd00::1]:80", "224.0.0.1:80"};
            for (String t : targets) check("guard CONNECT refuses " + t, connect(p, t).startsWith("HTTP/1.1 403"), connect(p, t));
            String lan = lanAddress();
            if (lan != null) {
                check("guard CONNECT refuses console LAN " + lan, connect(p, lan + ":80").startsWith("HTTP/1.1 403"), null);
                check("guard GET refuses console LAN " + lan, get(p, "http://" + lan + ":80/").startsWith("HTTP/1.1 403"), null);
            }
            for (String u : new String[]{"http://127.0.0.1:" + sp + "/secret", "http://localhost:" + sp + "/secret",
                    "http://[::1]:" + sp + "/", "http://2130706433:" + sp + "/", "http://rebind.test:" + sp + "/secret",
                    "http://169.254.169.254/latest/meta-data/"})
                check("guard GET refuses " + u, get(p, u).startsWith("HTTP/1.1 403"), get(p, u));
            check("guard rejects https absolute-form", get(p, "https://public.test/").startsWith("HTTP/1.1 400"), null);
            check("guard rejects userinfo", get(p, "http://u:p@public.test/").startsWith("HTTP/1.1 400"), null);

            // DNS rebinding: the name was public when checked earlier; it is private when JD connects.
            fakeDns(true);
            check("flip.test public at submit time", OmniPublicAddress.isPublic(InetAddress.getAllByName("flip.test")[0]), null);
            fakeDns(false);
            check("guard refuses flip.test after rebind", connect(p, "flip.test:" + sp).startsWith("HTTP/1.1 403"), null);
            check("guard GET refuses flip.test after rebind", get(p, "http://flip.test:" + sp + "/secret").startsWith("HTTP/1.1 403"), null);

            // Plain java.net sockets: only the guard.
            for (String host : new String[]{"127.0.0.1", "localhost"}) {
                try (Socket s = new Socket()) { s.connect(new InetSocketAddress(host, sp), 3000); check("plain socket refused " + host, false, "connected"); }
                catch (IOException e) { check("plain socket refused " + host, true, null); }
            }
            // java.net.URL: goes to the guard, which refuses.
            HttpURLConnection c = (HttpURLConnection) URI.create("http://127.0.0.1:" + sp + "/secret").toURL().openConnection();
            check("URL connection to loopback refused by guard", c.getResponseCode() == 403, String.valueOf(c.getResponseCode()));
            HttpURLConnection c2 = (HttpURLConnection) URI.create("http://127.0.0.1:" + sp + "/secret").toURL().openConnection(Proxy.NO_PROXY);
            try { c2.getResponseCode(); check("URL connection with NO_PROXY refused", false, "answered"); }
            catch (IOException e) { check("URL connection with NO_PROXY refused", true, null); }

            // JDownloader's socket factory: direct sockets (the "no proxy" fallback) fail, even for literals.
            Socket jdDirect = org.appwork.utils.net.SocketFactory.get().create((org.appwork.utils.net.httpconnection.HTTPConnection) null, null);
            try { jdDirect.connect(new InetSocketAddress("127.0.0.1", sp), 3000); check("JD socket direct refused", false, "connected"); }
            catch (IOException e) { check("JD socket direct refused", e.getMessage().startsWith(OmniPublicAddress.POLICY), e.getMessage()); }
            finally { jdDirect.close(); }
            // JDownloader's HTTP stack with HTTPProxy.NONE (what ProxyController's fallback hands out).
            try {
                org.appwork.utils.net.httpconnection.HTTPConnection h = org.appwork.utils.net.httpconnection.HTTPConnectionFactory
                    .createHTTPConnection(URI.create("http://127.0.0.1:" + sp + "/secret").toURL(), org.appwork.utils.net.httpconnection.HTTPProxy.NONE);
                h.connect();
                check("JD HTTP with NONE proxy refused", false, String.valueOf(h.getResponseCode()));
            } catch (IOException e) { check("JD HTTP with NONE proxy refused", true, null); }
            // JDownloader's HTTP stack with the guard as its proxy: refused with 403 by the guard.
            try {
                org.appwork.utils.net.httpconnection.HTTPProxy gp = new org.appwork.utils.net.httpconnection.HTTPProxy(
                    org.appwork.utils.net.httpconnection.HTTPProxy.TYPE.HTTP, "127.0.0.1", p.port());
                org.appwork.utils.net.httpconnection.HTTPConnection h = org.appwork.utils.net.httpconnection.HTTPConnectionFactory
                    .createHTTPConnection(URI.create("http://127.0.0.1:" + sp + "/secret").toURL(), gp);
                h.connect();
                check("JD HTTP via guard to loopback refused", h.getResponseCode() == 403, String.valueOf(h.getResponseCode()));
            } catch (IOException e) { check("JD HTTP via guard to loopback refused", true, e.getClass().getSimpleName()); }

            // Raw java.net sockets to literal private addresses, with and without NO_PROXY, and over SSL.
            for (Socket raw : new Socket[]{new Socket(), new Socket(Proxy.NO_PROXY)}) {
                try (Socket r = raw) { r.connect(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), sp), 3000); check("raw socket to literal loopback refused", false, "connected"); }
                catch (IOException e) { check("raw socket to literal loopback refused", true, null); }
            }
            try (Socket ssl = javax.net.ssl.SSLSocketFactory.getDefault().createSocket("127.0.0.1", sp)) { check("SSL socket to loopback refused", false, "connected"); }
            catch (IOException e) { check("SSL socket to loopback refused", true, null); }
            check("secret server never contacted", secret.hits.get() == 0, String.valueOf(secret.hits.get()));
            Map<String, Object> status = p.status(false);
            check("status: policy withheld until JD is ready", status.get("policy") == null && "JDownloader is initializing".equals(status.get("problem")), status.toString());
            check("status: layers healthy", Boolean.TRUE.equals(status.get("guard")) && Boolean.TRUE.equals(status.get("resolver"))
                && Boolean.TRUE.equals(status.get("proxy_selector")) && Boolean.TRUE.equals(status.get("socket_factory")), status.toString());
            check("status: refusals counted", ((Number) status.get("refused")).longValue() > 20, status.toString());
            // Tampering: replacing a layer drops the policy for the rest of the session.
            java.net.ProxySelector mine = java.net.ProxySelector.getDefault();
            java.net.ProxySelector.setDefault(null);
            Map<String, Object> tampered = p.status(false);
            java.net.ProxySelector.setDefault(mine);
            Map<String, Object> after = p.status(false);
            check("status: replaced selector is reported", "JVM proxy selector was replaced".equals(tampered.get("problem")), tampered.toString());
            check("status: tampering is sticky", "JVM proxy selector was replaced".equals(after.get("problem")), after.toString());
        }
    }

    /** Fake DNS for the tests: answers come from this table, then pass through the real filter. */
    static final Map<String, String[]> DNS = new java.util.concurrent.ConcurrentHashMap<>();

    static void fakeDns(boolean flipPublic) {
        DNS.put("rebind.test", new String[]{"10.0.0.5"});
        DNS.put("lan6.test", new String[]{"fd00::5"});
        DNS.put("mixed.test", new String[]{"93.184.215.14", "10.0.0.6"});
        DNS.put("loop.test", new String[]{"127.0.0.1"});
        DNS.put("cgnat.test", new String[]{"100.64.1.1"});
        DNS.put("meta.test", new String[]{"169.254.169.254"});
        DNS.put("mapped.test", new String[]{"::ffff:192.168.1.20"});
        DNS.put("public.test", new String[]{"93.184.215.14"});
        DNS.put("flip.test", new String[]{flipPublic ? "93.184.215.14" : "127.0.0.1"});
        OmniPublicResolverProvider.upstreamForTests = new java.net.spi.InetAddressResolver() {
            public java.util.stream.Stream<InetAddress> lookupByName(String host, LookupPolicy policy) throws java.net.UnknownHostException {
                String[] answers = DNS.get(host.toLowerCase(java.util.Locale.ROOT));
                if (answers == null) throw new java.net.UnknownHostException(host);
                List<InetAddress> out = new ArrayList<>();
                for (String a : answers) out.add(InetAddress.getByAddress(host, InetAddress.getByName(a).getAddress()));
                return out.stream();
            }
            public String lookupByAddress(byte[] addr) throws java.net.UnknownHostException { throw new java.net.UnknownHostException(); }
        };
    }

    static boolean refusedByResolver(String name) {
        try { InetAddress.getAllByName(name); return false; }
        catch (java.net.UnknownHostException e) { return e.getMessage() != null && e.getMessage().startsWith(OmniPublicAddress.POLICY); }
    }

    // ------------------------------------------------------------------------------------------
    static void redirect() throws Exception {
        try (Server secret = new Server("127.0.0.1", null)) {
            int sp = secret.port();
            String target = "http://127.0.0.1:" + sp + "/secret";
            try (Server redirector = new Server("127.0.0.7", target); Server redirector2 = new Server("127.0.0.7", "http://169.254.169.254/latest/meta-data/")) {
                InetAddress alias = ip("127.0.0.7");
                OmniEgressPolicy p = OmniEgressPolicy.install(a -> OmniPublicAddress.isPublic(a) || a.equals(alias));
                check("redirect: alias reachable through guard", get(p, "http://127.0.0.7:" + redirector.port() + "/").startsWith("HTTP/1.1 302"), null);
                // java.net.URL follows the redirect; the second hop goes through the guard and is refused.
                HttpURLConnection c = (HttpURLConnection) URI.create("http://127.0.0.7:" + redirector.port() + "/start").toURL().openConnection();
                c.setInstanceFollowRedirects(true);
                int code = c.getResponseCode();
                check("redirect: URL 302 to loopback ends at guard 403", code == 403, String.valueOf(code));
                // JDownloader's own HTTP stack (jd.http.Browser follows redirects) with the guard as proxy.
                int hitsBefore = redirector.hits.get();
                String body = null;
                try {
                    jd.http.Browser br = new jd.http.Browser();
                    br.setProxySelector(new jd.http.StaticProxySelector(new org.appwork.utils.net.httpconnection.HTTPProxy(
                        org.appwork.utils.net.httpconnection.HTTPProxy.TYPE.HTTP, "127.0.0.1", p.port())));
                    br.setFollowRedirects(true);
                    body = br.getPage("http://127.0.0.7:" + redirector.port() + "/jd");
                } catch (Throwable e) {
                    body = "error " + e.getClass().getSimpleName();
                }
                check("redirect: JD Browser reached the redirector", redirector.hits.get() > hitsBefore, String.valueOf(body));
                check("redirect: JD Browser never got the secret", body == null || !body.contains("secret"), body);
                // Browser with no proxy at all (the "none" fallback): the socket factory refuses outright.
                hitsBefore = redirector.hits.get();
                try {
                    jd.http.Browser br = new jd.http.Browser();
                    br.setProxySelector(new jd.http.StaticProxySelector(org.appwork.utils.net.httpconnection.HTTPProxy.NONE));
                    String direct = br.getPage("http://127.0.0.7:" + redirector.port() + "/direct");
                    check("redirect: JD Browser direct refused", false, direct);
                } catch (Throwable e) {
                    check("redirect: JD Browser direct refused", redirector.hits.get() == hitsBefore, e.getClass().getSimpleName());
                }
                HttpURLConnection c3 = (HttpURLConnection) URI.create("http://127.0.0.7:" + redirector2.port() + "/meta").toURL().openConnection();
                check("redirect: 302 to metadata address refused", c3.getResponseCode() == 403, String.valueOf(c3.getResponseCode()));
                check("redirect: secret server never contacted", secret.hits.get() == 0, String.valueOf(secret.hits.get()));
            }
        }
    }

    // ------------------------------------------------------------------------------------------
    static void online() throws Exception {
        OmniEgressPolicy p = OmniEgressPolicy.install();
        check("online: CONNECT example.com:443", connect(p, "example.com:443").startsWith("HTTP/1.1 200"), null);
        HttpURLConnection https = (HttpURLConnection) URI.create("https://example.com/").toURL().openConnection();
        check("online: java.net.URL https via guard", https.getResponseCode() == 200, String.valueOf(https.getResponseCode()));
        HttpURLConnection http = (HttpURLConnection) URI.create("http://example.com/").toURL().openConnection();
        check("online: java.net.URL http via guard", http.getResponseCode() == 200, String.valueOf(http.getResponseCode()));
        jd.http.Browser br = new jd.http.Browser();
        br.setProxySelector(new jd.http.StaticProxySelector(new org.appwork.utils.net.httpconnection.HTTPProxy(
            org.appwork.utils.net.httpconnection.HTTPProxy.TYPE.HTTP, "127.0.0.1", p.port())));
        br.setFollowRedirects(true);
        String page = br.getPage("http://www.rfc-editor.org/rfc/rfc2606.txt");
        check("online: JD Browser https (redirects followed) via guard", page != null && page.contains("Reserved Top Level DNS Names"), page == null ? "null" : page.substring(0, Math.min(80, page.length())));
        String plain = br.getPage("http://example.com/");
        check("online: JD Browser http via guard", plain != null && plain.contains("Example Domain"), null);
        check("online: allowed counted", p.allowed.get() >= 4, String.valueOf(p.allowed.get()));
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length > 0 ? args[0] : "unit";
        if (mode.equals("prod") || mode.equals("redirect")) fakeDns(false);
        switch (mode) {
            case "unit": unit(); break;
            case "prod": prod(); break;
            case "redirect": redirect(); break;
            case "online": online(); break;
            default: throw new IllegalArgumentException(mode);
        }
        System.out.println("RESULT " + mode + " passed=" + passed + " failed=" + failed + (failures.isEmpty() ? "" : " " + failures));
        System.exit(failed == 0 ? 0 : 1);
    }
}
