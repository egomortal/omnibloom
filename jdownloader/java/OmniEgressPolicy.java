// SPDX-License-Identifier: GPL-3.0-or-later
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ConnectException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketAddress;
import java.net.SocketTimeoutException;
import java.net.URI;
import java.net.URL;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Predicate;

/**
 * Egress policy omni-public-only-v1 for JDownloader 2 on the PS5 (audit JD-03).
 *
 * Every connection JDownloader makes may only reach public addresses. Layers, all installed before
 * JDownloader starts and all re-checked on every health call:
 *
 *  1. Guard proxy (this class): a forward proxy on 127.0.0.1 only, the Java twin of downloader-7's
 *     egress_guard.py. Each CONNECT tunnel and each plain HTTP request is resolved once, refused unless
 *     every answer is a public unicast address outside the console's subnets, and the outgoing socket is
 *     pinned to the checked address (no second lookup, so no DNS rebinding). One request per connection.
 *  2. JDownloader's ProxyController: our guard is the only enabled proxy ("no proxy" is disabled, proxy
 *     auto-detection, reconnect, local UPnP IP checks and automatic update checks are off).
 *  3. AppWork socket factory: every socket JDownloader's HTTP stack opens (plugins, redirects, sub-requests,
 *     the updater, SOCKS paths) may connect to the guard only. A "no proxy" fallback anywhere in JDownloader
 *     therefore fails instead of going direct.
 *  4. JVM sockets: java.net.URL connections go to the guard (ProxySelector), and every java.net.Socket in the
 *     JVM gets a checked implementation (Socket.setSocketImplFactory) that connects only to the guard or to a
 *     public address. This also covers "no proxy" URL connections, SSL sockets and raw plugin sockets.
 *  5. JVM resolver (OmniPublicResolverProvider): names that resolve to local or private addresses fail.
 *
 * The bridge reports egress_policy only while all layers are in place and JDownloader's proxy list is
 * verified. If any layer can't be installed, JDownloader is not started at all.
 */
public final class OmniEgressPolicy {
    public static final String POLICY = OmniPublicAddress.POLICY;
    static final String PROBE_SUFFIX = ".omni-egress-probe.invalid";
    private static final int HEAD_LIMIT = 64 * 1024, MAX_CONNECTIONS = 24;
    private static final int RESOLVE_TIMEOUT_MS = 8000, CONNECT_TIMEOUT_MS = 10000, HEAD_TIMEOUT_MS = 10000;
    private static final long IDLE_NANOS = TimeUnit.SECONDS.toNanos(120);
    private static final int POLL_MS = 5000;
    private static final Set<String> HOP_HEADERS = new HashSet<>(Arrays.asList("connection", "keep-alive",
        "proxy-connection", "proxy-authorization", "proxy-authenticate", "te", "trailer", "upgrade"));
    private static volatile OmniEgressPolicy active;

    private final ServerSocket server;
    private final int port;
    private final InetAddress loopback;
    private final Semaphore slots = new Semaphore(MAX_CONNECTIONS);
    private final ExecutorService resolvers = Executors.newCachedThreadPool(daemon("omni-egress-resolve"));
    final AtomicLong allowed = new AtomicLong(), refused = new AtomicLong(), refusedDirect = new AtomicLong();
    private final AtomicInteger probes = new AtomicInteger();
    private final Selector selector;
    private Object socketFactory;            // org.appwork.utils.net.SocketFactory once installed
    private volatile String tampered = "";
    private volatile boolean closed;
    private final Predicate<InetAddress> allow;

    private static java.util.concurrent.ThreadFactory daemon(String name) {
        return task -> { Thread t = new Thread(task, name); t.setDaemon(true); return t; };
    }

    OmniEgressPolicy(Predicate<InetAddress> allow) throws IOException {
        this.allow = allow;
        loopback = InetAddress.getByAddress("127.0.0.1", new byte[]{127, 0, 0, 1});
        server = new ServerSocket();
        server.bind(new InetSocketAddress(loopback, 0), 32);
        port = server.getLocalPort();
        selector = new Selector();               // after port/loopback: it hands out the guard's address
        Thread accept = new Thread(this::accept, "omni-egress-guard");
        accept.setDaemon(true);
        accept.start();
    }

    public int port() { return port; }

    static OmniEgressPolicy current() { return active; }

    // ---------------------------------------------------------------------------------------------
    // Installation and self-tests

    /** Installs every JVM layer and proves each one with a self-test. Throws if any layer is missing. */
    public static OmniEgressPolicy install() throws Exception {
        return install(OmniPublicAddress::isPublic);
    }

    /** Package-private so PC tests can widen "public" to one loopback alias; production uses install(). */
    static synchronized OmniEgressPolicy install(Predicate<InetAddress> allow) throws Exception {
        if (active != null) return active;
        OmniEgressPolicy policy = new OmniEgressPolicy(allow);
        try {
            String failure = policy.selfTestResolver();
            if (failure != null) throw new IllegalStateException(failure);
            ProxySelector.setDefault(policy.selector);
            CheckedSocketImpl.install(policy);
            policy.socketFactory = JdSockets.install(policy);
            failure = policy.selfTestGuard();
            if (failure == null) failure = policy.selfTestSockets();
            if (failure != null) throw new IllegalStateException(failure);
        } catch (Throwable error) {
            policy.close();
            throw error instanceof Exception ? (Exception) error : new IllegalStateException(error);
        }
        active = policy;
        return policy;
    }

    void close() {
        closed = true;
        try { server.close(); } catch (IOException ignored) { }
        resolvers.shutdownNow();
    }

    /** null when the JVM resolver is ours and refuses; otherwise the problem. Causes no DNS traffic. */
    String selfTestResolver() {
        if (!OmniPublicResolverProvider.installed()) {
            // The resolver is loaded on the first lookup; this lookup loads it.
            probeLookup();
        }
        if (!OmniPublicResolverProvider.installed()) return "JVM resolver filter is not installed";
        String outcome = probeLookup();
        return outcome == null ? null : outcome;
    }

    private String probeLookup() {
        String name = "r" + probes.incrementAndGet() + "-" + Long.toHexString(System.nanoTime()) + PROBE_SUFFIX;
        try {
            InetAddress.getAllByName(name);
            return "JVM resolver answered a reserved probe name";
        } catch (UnknownHostException expected) {
            String message = expected.getMessage();
            return message != null && message.startsWith(POLICY) ? null : "JVM resolver is not the policy resolver";
        }
    }

    /** The guard must refuse a loopback literal and a private-only name, with 403. */
    String selfTestGuard() {
        for (String target : new String[]{"127.0.0.1:" + port, "[::1]:443", "10.0.0.1:80",
                                          "g" + probes.incrementAndGet() + PROBE_SUFFIX + ":443"}) {
            try (Socket s = new Socket(Proxy.NO_PROXY)) {
                s.connect(new InetSocketAddress(loopback, port), CONNECT_TIMEOUT_MS);
                s.setSoTimeout(CONNECT_TIMEOUT_MS);
                s.getOutputStream().write(("CONNECT " + target + " HTTP/1.1\r\nHost: " + target + "\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
                byte[] head = new byte[12];
                int at = 0;
                InputStream in = s.getInputStream();
                while (at < head.length) { int n = in.read(head, at, head.length - at); if (n < 0) break; at += n; }
                String line = new String(head, 0, at, StandardCharsets.ISO_8859_1);
                if (!line.startsWith("HTTP/1.1 403")) return "Guard proxy did not refuse a private target";
            } catch (IOException error) {
                return "Guard proxy self-test failed: " + error.getClass().getSimpleName();
            }
        }
        return null;
    }

    /** Plain sockets and JDownloader's sockets may reach the guard and nothing else. */
    String selfTestSockets() {
        if (ProxySelector.getDefault() != selector) return "JVM proxy selector was not installed";
        try (Socket ok = new Socket()) {
            ok.connect(new InetSocketAddress(loopback, port), CONNECT_TIMEOUT_MS);
        } catch (IOException error) {
            return "Plain socket could not reach the guard: " + error.getClass().getSimpleName();
        }
        // The target listens, so only the policy (not a closed port) can make this connect fail.
        try (ServerSocket target = new ServerSocket()) {
            target.bind(new InetSocketAddress(loopback, 0), 1);
            long before = refusedDirect.get();
            try (Socket direct = new Socket()) {
                direct.connect(new InetSocketAddress(loopback, target.getLocalPort()), CONNECT_TIMEOUT_MS);
                return "Plain socket connected around the guard";
            } catch (IOException expected) {
                if (refusedDirect.get() == before) return "Plain socket was not checked by the proxy selector";
            }
            try (Socket noProxy = new Socket(Proxy.NO_PROXY)) {
                noProxy.connect(new InetSocketAddress(loopback, target.getLocalPort()), CONNECT_TIMEOUT_MS);
                return "Direct (no proxy) socket connected around the guard";
            } catch (IOException expected) {
                if (expected.getMessage() == null || !expected.getMessage().startsWith(POLICY)) return "Direct socket was not checked";
            }
            String jd = JdSockets.selfTest(this, target.getLocalPort());
            if (jd != null) return jd;
        } catch (IOException error) {
            return "Socket self-test failed: " + error.getClass().getSimpleName();
        }
        return null;
    }

    // ---------------------------------------------------------------------------------------------
    // Status

    /** The layers' state for the health reply. `jdReady` adds JDownloader's proxy list check. */
    public Map<String, Object> status(boolean jdReady) {
        Map<String, Object> out = new LinkedHashMap<>();
        boolean guard = !closed && !server.isClosed();
        String resolver = selfTestResolver();
        boolean selectorOk = ProxySelector.getDefault() == selector;
        boolean factoryOk = JdSockets.installed(this) && CheckedSocketImpl.installedFor(this);
        if (!selectorOk || !factoryOk) {
            // Something replaced a layer while JDownloader ran. Never report the policy again this session.
            if (tampered.isEmpty()) tampered = !selectorOk ? "JVM proxy selector was replaced" : "JDownloader socket factory was replaced";
        }
        String jd = jdReady ? JdProxies.verify(this) : "JDownloader is initializing";
        String problem = !guard ? "Guard proxy stopped" : resolver != null ? resolver : !tampered.isEmpty() ? tampered
            : jd != null ? jd : null;
        out.put("policy", problem == null ? POLICY : null);
        out.put("guard", guard);
        out.put("resolver", resolver == null);
        out.put("proxy_selector", selectorOk);
        out.put("socket_factory", factoryOk);
        out.put("jd_proxy", jdReady ? jd == null : null);
        out.put("console_subnets", OmniPublicAddress.consoleSubnets());
        out.put("allowed", allowed.get());
        out.put("refused", refused.get());
        out.put("refused_direct", refusedDirect.get());
        out.put("problem", problem == null ? "" : problem);
        return out;
    }

    /** The policy name while every layer holds; null otherwise. */
    public String activePolicy(boolean jdReady) {
        return (String) status(jdReady).get("policy");
    }

    boolean isGuard(SocketAddress endpoint) {
        if (!(endpoint instanceof InetSocketAddress)) return false;
        InetSocketAddress a = (InetSocketAddress) endpoint;
        InetAddress ip = a.getAddress();
        return !a.isUnresolved() && a.getPort() == port && ip != null && Arrays.equals(ip.getAddress(), loopback.getAddress());
    }

    // ---------------------------------------------------------------------------------------------
    // Layer 4: JVM ProxySelector

    final class Selector extends ProxySelector {
        private final Proxy guardProxy = new Proxy(Proxy.Type.HTTP, new InetSocketAddress(loopback, port));
        // A raw socket given a SOCKS proxy never falls back to a direct connection when the proxy fails (the JDK goes
        // direct for any non-SOCKS answer). This one is an unresolvable .invalid name: the connect fails before any
        // packet is sent. For URL schemes other than http/https the same answer makes the handler fail.
        private final Proxy refuse = new Proxy(Proxy.Type.SOCKS, InetSocketAddress.createUnresolved("refused" + PROBE_SUFFIX, 1080));

        @Override
        public List<Proxy> select(URI uri) {
            if (uri == null) throw new IllegalArgumentException("URI can't be null");
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
            if (scheme.equals("http") || scheme.equals("https")) return Collections.singletonList(guardProxy);
            if (scheme.equals("socket") && uri.getPort() == port && "127.0.0.1".equals(uri.getHost()))
                return Collections.singletonList(Proxy.NO_PROXY);
            refusedDirect.incrementAndGet();
            return Collections.singletonList(refuse);
        }

        @Override
        public void connectFailed(URI uri, SocketAddress address, IOException failure) { }
    }

    // ---------------------------------------------------------------------------------------------
    // Layer 1: guard proxy

    static final class Refused extends Exception {
        private static final long serialVersionUID = 1L;
        Refused(String why) { super(why); }
    }

    private void accept() {
        while (!closed) {
            Socket client;
            try {
                client = server.accept();
            } catch (IOException stopped) {
                if (closed || server.isClosed()) return;
                continue;
            }
            if (!client.getInetAddress().isLoopbackAddress()) { quiet(client); continue; }
            if (!slots.tryAcquire()) { reply(client, 503, "Busy"); continue; }
            Thread worker = new Thread(() -> {
                try { serve(client); } finally { slots.release(); }
            }, "omni-egress");
            worker.setDaemon(true);
            worker.start();
        }
    }

    private static void quiet(Socket s) {
        if (s == null) return;
        try { s.close(); } catch (IOException ignored) { }
    }

    private static void reply(Socket client, int code, String text) {
        try {
            client.getOutputStream().write(("HTTP/1.1 " + code + " " + text + "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                .getBytes(StandardCharsets.ISO_8859_1));
            client.getOutputStream().flush();
        } catch (IOException ignored) {
        } finally {
            quiet(client);
        }
    }

    /** Reads the request head (up to the blank line); returns {head, leftover bytes}. */
    private static Object[] readHead(Socket client) throws IOException {
        client.setSoTimeout(HEAD_TIMEOUT_MS);
        InputStream in = client.getInputStream();
        ByteArrayOutputStream data = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        while (true) {
            int n = in.read(buffer);
            if (n < 0) throw new IOException("closed");
            data.write(buffer, 0, n);
            byte[] all = data.toByteArray();
            for (int i = 0; i + 3 < all.length; i++) {
                if (all[i] == '\r' && all[i + 1] == '\n' && all[i + 2] == '\r' && all[i + 3] == '\n') {
                    return new Object[]{new String(all, 0, i, StandardCharsets.ISO_8859_1), Arrays.copyOfRange(all, i + 4, all.length)};
                }
            }
            if (all.length > HEAD_LIMIT) throw new IOException("head too large");
        }
    }

    static String[] splitHostPort(String text, int defaultPort) {
        String t = text.trim(), host;
        int port = defaultPort;
        if (t.startsWith("[")) {
            int end = t.indexOf(']');
            if (end < 0) throw new IllegalArgumentException("bad host");
            host = t.substring(1, end);
            String rest = t.substring(end + 1);
            if (rest.startsWith(":")) port = Integer.parseInt(rest.substring(1));
            else if (!rest.isEmpty()) throw new IllegalArgumentException("bad host");
        } else if (t.indexOf(':') >= 0 && t.indexOf(':') == t.lastIndexOf(':')) {
            host = t.substring(0, t.indexOf(':'));
            port = Integer.parseInt(t.substring(t.indexOf(':') + 1));
        } else {
            host = t;
        }
        if (host.isEmpty() || port < 1 || port > 65535) throw new IllegalArgumentException("bad host or port");
        return new String[]{host, Integer.toString(port)};
    }

    /** All addresses a host may be reached at, each checked; refused unless every answer is public. */
    InetAddress[] check(String host) throws Refused, IOException {
        InetAddress literal = OmniPublicAddress.literal(host);
        InetAddress[] found;
        if (literal != null) {
            found = new InetAddress[]{literal};
        } else {
            if (OmniPublicAddress.numericLooking(host)) throw new Refused("numeric host name");
            String lower = host.toLowerCase(Locale.ROOT);
            if (lower.equals("localhost") || lower.endsWith(".localhost") || lower.equals("localhost.")) throw new Refused("loopback name");
            if (!host.matches("[A-Za-z0-9._-]{1,253}")) throw new IOException("bad host name");
            // Fresh lookup per connection through the system resolver, checked here (not via the JVM-wide filter or
            // InetAddress's cache), so this layer stands on its own and the answer it checks is the one it pins.
            java.net.spi.InetAddressResolver upstream = OmniPublicResolverProvider.upstream();
            if (upstream == null) throw new IOException("resolver not installed");
            if (host.toLowerCase(Locale.ROOT).endsWith(".invalid")) throw new Refused("reserved name");
            Future<InetAddress[]> lookup = resolvers.submit((Callable<InetAddress[]>) () -> upstream.lookupByName(host,
                java.net.spi.InetAddressResolver.LookupPolicy.of(java.net.spi.InetAddressResolver.LookupPolicy.IPV4
                    | java.net.spi.InetAddressResolver.LookupPolicy.IPV6)).toArray(InetAddress[]::new));
            try {
                found = lookup.get(RESOLVE_TIMEOUT_MS, TimeUnit.MILLISECONDS);
            } catch (TimeoutException slow) {
                lookup.cancel(true);
                throw new SocketTimeoutException("address lookup timed out");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IOException("interrupted");
            } catch (ExecutionException failed) {
                throw new IOException("address lookup failed");
            }
        }
        if (found == null || found.length == 0) throw new IOException("no address");
        for (InetAddress a : found) if (!allow.test(a)) throw new Refused("local or private address");
        return found;
    }

    /** Connects to a checked (pinned) address; never looks the name up again. */
    private Socket open(String host, int port) throws Refused, IOException {
        InetAddress[] addresses = check(host);
        IOException last = null;
        for (InetAddress address : addresses) {
            Socket upstream = new Socket(Proxy.NO_PROXY);
            try {
                upstream.connect(new InetSocketAddress(address, port), CONNECT_TIMEOUT_MS);
                return upstream;
            } catch (IOException failed) {
                quiet(upstream);
                last = failed;
            }
        }
        throw last == null ? new IOException("connect failed") : last;
    }

    private void serve(Socket client) {
        Socket upstream = null;
        try {
            Object[] parsed;
            try { parsed = readHead(client); } catch (IOException bad) { return; }
            String head = (String) parsed[0];
            byte[] rest = (byte[]) parsed[1];
            String[] lines = head.split("\r\n", -1);
            String[] parts = lines[0].split(" ");
            if (parts.length != 3 || !parts[2].startsWith("HTTP/1.") || !parts[0].matches("[A-Za-z]{1,16}")) { reply(client, 400, "Bad Request"); return; }
            String method = parts[0], target = parts[1];
            try {
                if (method.equalsIgnoreCase("CONNECT")) {
                    String[] hp = splitHostPort(target, 443);
                    upstream = open(hp[0], Integer.parseInt(hp[1]));
                    allowed.incrementAndGet();
                    OutputStream out = client.getOutputStream();
                    out.write("HTTP/1.1 200 Connection established\r\n\r\n".getBytes(StandardCharsets.ISO_8859_1));
                    out.flush();
                    if (rest.length > 0) upstream.getOutputStream().write(rest);
                } else {
                    URI url = new URI(target);
                    if (!"http".equalsIgnoreCase(url.getScheme()) || url.getHost() == null || url.getRawUserInfo() != null) { reply(client, 400, "Bad Request"); return; }
                    String host = url.getHost();
                    if (host.startsWith("[") && host.endsWith("]")) host = host.substring(1, host.length() - 1);
                    int port = url.getPort() < 0 ? 80 : url.getPort();
                    if (port < 1 || port > 65535) { reply(client, 400, "Bad Request"); return; }
                    upstream = open(host, port);
                    allowed.incrementAndGet();
                    String path = url.getRawPath() == null || url.getRawPath().isEmpty() ? "/" : url.getRawPath();
                    if (url.getRawQuery() != null) path += "?" + url.getRawQuery();
                    StringBuilder out = new StringBuilder(head.length() + 64);
                    out.append(method).append(' ').append(path).append(" HTTP/1.1\r\n");
                    boolean seenHost = false;
                    for (int i = 1; i < lines.length; i++) {
                        String line = lines[i];
                        if (line.isEmpty()) continue;
                        String name = line.split(":", 2)[0].trim().toLowerCase(Locale.ROOT);
                        if (HOP_HEADERS.contains(name)) continue;
                        seenHost |= name.equals("host");
                        out.append(line).append("\r\n");
                    }
                    if (!seenHost) out.append("Host: ").append(url.getRawAuthority()).append("\r\n");
                    out.append("Connection: close\r\n\r\n");
                    OutputStream up = upstream.getOutputStream();
                    up.write(out.toString().getBytes(StandardCharsets.ISO_8859_1));
                    if (rest.length > 0) up.write(rest);
                    up.flush();
                }
            } catch (Refused no) {
                refused.incrementAndGet();
                reply(client, 403, "Forbidden");
                return;
            } catch (SocketTimeoutException slow) {
                reply(client, 504, "Gateway Timeout");
                return;
            } catch (Exception failed) {       // lookup failures, bad targets, connect errors
                reply(client, 502, "Bad Gateway");
                return;
            }
            relay(client, upstream);
        } finally {
            quiet(client);
            quiet(upstream);
        }
    }

    /** Copies both ways until the upstream side ends, or nothing moves for IDLE in either direction. */
    private void relay(Socket client, Socket upstream) {
        AtomicLong last = new AtomicLong(System.nanoTime());
        Thread up = new Thread(() -> {
            if (pump(client, upstream, last)) {
                try { upstream.shutdownOutput(); } catch (IOException ignored) { }
            } else {
                quiet(upstream);
            }
        }, "omni-egress-up");
        up.setDaemon(true);
        up.start();
        pump(upstream, client, last);
        quiet(client);
        quiet(upstream);
    }

    /** true on a clean end of stream; false on error or idle timeout. */
    private boolean pump(Socket from, Socket to, AtomicLong last) {
        byte[] buffer = new byte[65536];
        try {
            from.setSoTimeout(POLL_MS);
            InputStream in = from.getInputStream();
            OutputStream out = to.getOutputStream();
            while (true) {
                int n;
                try {
                    n = in.read(buffer);
                } catch (SocketTimeoutException poll) {
                    if (System.nanoTime() - last.get() > IDLE_NANOS) return false;
                    continue;
                }
                if (n < 0) return true;
                out.write(buffer, 0, n);
                last.set(System.nanoTime());
            }
        } catch (IOException ended) {
            return false;
        }
    }

    // ---------------------------------------------------------------------------------------------
    // Layer 4b: every java.net.Socket in the JVM

    /**
     * A java.net.Socket implementation backed by a SocketChannel (public API, so no JDK internals are needed). It
     * refuses to connect anywhere except the guard or a public address. Installed once per JVM with
     * Socket.setSocketImplFactory, which can't be replaced afterwards. Server sockets are unaffected.
     */
    static final class CheckedSocketImpl extends java.net.SocketImpl {
        private static volatile OmniEgressPolicy owner;
        private final OmniEgressPolicy policy;
        private java.nio.channels.SocketChannel channel;
        private Socket adaptor;

        CheckedSocketImpl(OmniEgressPolicy policy) { this.policy = policy; }

        @SuppressWarnings("deprecation")
        static void install(OmniEgressPolicy policy) throws IOException {
            owner = policy;
            Socket.setSocketImplFactory(() -> new CheckedSocketImpl(owner));
        }

        static boolean installedFor(OmniEgressPolicy policy) { return owner == policy; }

        @Override protected void create(boolean stream) throws IOException {
            if (!stream) throw new java.net.SocketException("Datagram sockets are not supported");
            channel = java.nio.channels.SocketChannel.open();
            adaptor = channel.socket();
        }

        @Override protected void connect(String host, int port) throws IOException { connect(new InetSocketAddress(host, port), 0); }
        @Override protected void connect(InetAddress address, int port) throws IOException { connect(new InetSocketAddress(address, port), 0); }

        @Override protected void connect(SocketAddress endpoint, int timeout) throws IOException {
            if (!(endpoint instanceof InetSocketAddress)) throw new IllegalArgumentException("Unsupported address type");
            InetSocketAddress target = (InetSocketAddress) endpoint;
            if (target.isUnresolved()) throw new UnknownHostException(target.getHostName());
            if (!policy.isGuard(target) && !policy.allow.test(target.getAddress())) {
                policy.refusedDirect.incrementAndGet();
                throw new ConnectException(POLICY + ": connection to a local or private address refused");
            }
            adaptor.connect(target, timeout);
            address = target.getAddress();
            port = target.getPort();
            localport = adaptor.getLocalPort();
        }

        @Override protected void bind(InetAddress host, int port) throws IOException {
            adaptor.bind(new InetSocketAddress(host, port));
            localport = adaptor.getLocalPort();
        }

        @Override protected void listen(int backlog) throws IOException { throw new java.net.SocketException("Not a server socket"); }
        @Override protected void accept(java.net.SocketImpl s) throws IOException { throw new java.net.SocketException("Not a server socket"); }
        @Override protected InputStream getInputStream() throws IOException { return adaptor.getInputStream(); }
        @Override protected OutputStream getOutputStream() throws IOException { return adaptor.getOutputStream(); }
        @Override protected int available() throws IOException { return adaptor.getInputStream().available(); }
        @Override protected void close() throws IOException { if (channel != null) channel.close(); }
        @Override protected void shutdownInput() throws IOException { adaptor.shutdownInput(); }
        @Override protected void shutdownOutput() throws IOException { adaptor.shutdownOutput(); }
        @Override protected boolean supportsUrgentData() { return true; }
        @Override protected void sendUrgentData(int data) throws IOException { adaptor.sendUrgentData(data); }

        @Override public void setOption(int id, Object value) throws java.net.SocketException {
            switch (id) {
                case SO_TIMEOUT: adaptor.setSoTimeout((Integer) value); break;
                case TCP_NODELAY: adaptor.setTcpNoDelay((Boolean) value); break;
                case SO_KEEPALIVE: adaptor.setKeepAlive((Boolean) value); break;
                case SO_RCVBUF: adaptor.setReceiveBufferSize((Integer) value); break;
                case SO_SNDBUF: adaptor.setSendBufferSize((Integer) value); break;
                case SO_REUSEADDR: adaptor.setReuseAddress((Boolean) value); break;
                case SO_OOBINLINE: adaptor.setOOBInline((Boolean) value); break;
                case IP_TOS: adaptor.setTrafficClass((Integer) value); break;
                case SO_LINGER:
                    if (value instanceof Boolean) adaptor.setSoLinger((Boolean) value, 0);
                    else adaptor.setSoLinger(true, (Integer) value);
                    break;
                default: throw new java.net.SocketException("Unsupported option " + id);
            }
        }

        @Override public Object getOption(int id) throws java.net.SocketException {
            switch (id) {
                case SO_TIMEOUT: return adaptor.getSoTimeout();
                case TCP_NODELAY: return adaptor.getTcpNoDelay();
                case SO_KEEPALIVE: return adaptor.getKeepAlive();
                case SO_RCVBUF: return adaptor.getReceiveBufferSize();
                case SO_SNDBUF: return adaptor.getSendBufferSize();
                case SO_REUSEADDR: return adaptor.getReuseAddress();
                case SO_OOBINLINE: return adaptor.getOOBInline();
                case IP_TOS: return adaptor.getTrafficClass();
                case SO_LINGER: { int l = adaptor.getSoLinger(); return l < 0 ? (Object) Boolean.FALSE : (Object) Integer.valueOf(l); }
                case SO_BINDADDR: return adaptor.getLocalAddress();
                default: throw new java.net.SocketException("Unsupported option " + id);
            }
        }
    }

    // ---------------------------------------------------------------------------------------------
    // Layer 3: AppWork (JDownloader) socket factory

    static final class GuardedSocket extends Socket {
        private final OmniEgressPolicy policy;

        GuardedSocket(OmniEgressPolicy policy) {
            super(Proxy.NO_PROXY);
            this.policy = policy;
        }

        @Override
        public void connect(SocketAddress endpoint) throws IOException { connect(endpoint, 0); }

        @Override
        public void connect(SocketAddress endpoint, int timeout) throws IOException {
            if (!policy.isGuard(endpoint)) {
                policy.refusedDirect.incrementAndGet();
                throw new ConnectException(POLICY + ": JDownloader may only connect through Omni's public-address guard");
            }
            super.connect(endpoint, timeout);
        }
    }

    static final class JdSockets extends org.appwork.utils.net.SocketFactory {
        private final OmniEgressPolicy policy;

        JdSockets(OmniEgressPolicy policy) { this.policy = policy; }

        static Object install(OmniEgressPolicy policy) {
            JdSockets factory = new JdSockets(policy);
            org.appwork.utils.net.SocketFactory.set(factory);
            return factory;
        }

        static boolean installed(OmniEgressPolicy policy) {
            return policy.socketFactory != null && org.appwork.utils.net.SocketFactory.get() == policy.socketFactory;
        }

        static String selfTest(OmniEgressPolicy policy, int listening) {
            if (!installed(policy)) return "JDownloader socket factory was not installed";
            Socket direct = org.appwork.utils.net.SocketFactory.get().create((org.appwork.utils.net.httpconnection.HTTPConnection) null, null);
            try {
                direct.connect(new InetSocketAddress(policy.loopback, listening), CONNECT_TIMEOUT_MS);
                return "JDownloader socket connected around the guard";
            } catch (IOException expected) {
                String message = expected.getMessage();
                if (message == null || !message.startsWith(POLICY)) return "JDownloader socket was not checked";
            } finally {
                quiet(direct);
            }
            Socket guard = org.appwork.utils.net.SocketFactory.get().create((org.appwork.utils.net.httpconnection.HTTPConnection) null, null);
            try {
                guard.connect(new InetSocketAddress(policy.loopback, policy.port), CONNECT_TIMEOUT_MS);
            } catch (IOException error) {
                return "JDownloader socket could not reach the guard: " + error.getClass().getSimpleName();
            } finally {
                quiet(guard);
            }
            return null;
        }

        @Override
        public Socket createSocket(org.appwork.utils.net.httpconnection.HTTPConnection connection, InetAddress bind) {
            return new GuardedSocket(policy);
        }

        @Override
        public Socket create(org.appwork.utils.net.socketconnection.SocketConnection connection) {
            return new GuardedSocket(policy);
        }
    }

    // ---------------------------------------------------------------------------------------------
    // Layer 2: JDownloader's own proxy settings

    /** Before JDownloader starts: the guard is the only proxy, and nothing auto-detects or adds another. */
    public void configureJdownloader() {
        JdProxies.configure(this);
    }

    static final class JdProxies {
        static org.jdownloader.updatev2.ProxyData guardData(int port) {
            org.appwork.utils.net.httpconnection.HTTPProxyStorable proxy = new org.appwork.utils.net.httpconnection.HTTPProxyStorable();
            proxy.setType(org.appwork.utils.net.httpconnection.HTTPProxyStorable.TYPE.HTTP);
            proxy.setAddress("127.0.0.1");
            proxy.setPort(port);
            proxy.setConnectMethodPrefered(true);        // CONNECT for plain HTTP too: one code path in the guard
            proxy.setResolveHostName(false);             // the guard resolves and checks, JDownloader doesn't
            proxy.setPreferNativeImplementation(false);
            org.jdownloader.updatev2.ProxyData data = new org.jdownloader.updatev2.ProxyData();
            data.setProxy(proxy);
            data.setEnabled(true);
            data.setPac(false);
            data.setReconnectSupported(false);
            data.setRangeRequestsSupported(true);
            return data;
        }

        static void configure(OmniEgressPolicy policy) {
            org.appwork.utils.net.httpconnection.HTTPProxyStorable none = new org.appwork.utils.net.httpconnection.HTTPProxyStorable();
            none.setType(org.appwork.utils.net.httpconnection.HTTPProxyStorable.TYPE.NONE);
            org.jdownloader.updatev2.ProxyData noneData = new org.jdownloader.updatev2.ProxyData();
            noneData.setProxy(none);
            noneData.setEnabled(false);
            noneData.setPac(false);
            ArrayList<org.jdownloader.updatev2.ProxyData> list = new ArrayList<>();
            list.add(guardData(policy.port));
            list.add(noneData);
            org.jdownloader.updatev2.InternetConnectionSettings net = org.appwork.storage.config.JsonConfig.create(
                org.jdownloader.updatev2.InternetConnectionSettings.PATH, org.jdownloader.updatev2.InternetConnectionSettings.class);
            net.setProxyVoleAutodetectionEnabled(false);
            net.setLocalPacScript(null);
            net.setCustomProxyList(list);
            jd.controlling.reconnect.ReconnectConfig reconnect = org.appwork.storage.config.JsonConfig.create(jd.controlling.reconnect.ReconnectConfig.class);
            reconnect.setAutoReconnectEnabled(false);
            reconnect.setDownloadControllerPrefersReconnectEnabled(false);
            reconnect.setIPCheckAllowLocalUpnpIpCheckEnabled(false);
            reconnect.setIPCheckGloballyDisabled(true);
            org.appwork.storage.config.JsonConfig.create(org.jdownloader.updatev2.UpdateSettings.class).setAutoUpdateCheckEnabled(false);
        }

        private static boolean guardOnly(OmniEgressPolicy policy, List<org.appwork.utils.net.httpconnection.HTTPProxy> proxies) {
            if (proxies == null || proxies.isEmpty()) return false;
            for (org.appwork.utils.net.httpconnection.HTTPProxy p : proxies) {
                if (p == null || p.getType() != org.appwork.utils.net.httpconnection.HTTPProxy.TYPE.HTTP
                    || !"127.0.0.1".equals(p.getHost()) || p.getPort() != policy.port) return false;
            }
            return true;
        }

        /** null when every enabled selector is the guard and URL selection yields only the guard. Repairs once. */
        static String verify(OmniEgressPolicy policy) {
            try {
                jd.controlling.proxy.ProxyController controller = jd.controlling.proxy.ProxyController.getInstance();
                URL probe = URI.create("http://jd" + PROBE_SUFFIX + "/").toURL();
                boolean ours = false;
                for (jd.controlling.proxy.AbstractProxySelectorImpl s : controller.getList()) {
                    if (!s.isEnabled()) continue;
                    if (guardOnly(policy, s.getProxiesByURL(probe))) ours = true;
                    else controller.setEnabled(s, false);
                }
                if (!ours) controller.addProxy(new jd.controlling.proxy.SingleBasicProxySelectorImpl(guardData(policy.port)));
                for (jd.controlling.proxy.AbstractProxySelectorImpl s : controller.getList()) {
                    if (s.isEnabled() && !guardOnly(policy, s.getProxiesByURL(probe))) return "JDownloader has a proxy other than the guard";
                }
                if (!guardOnly(policy, controller.getProxiesByURL(probe))) return "JDownloader does not select the guard proxy";
                return null;
            } catch (Throwable error) {
                return "JDownloader proxy check failed: " + error.getClass().getSimpleName();
            }
        }
    }
}
