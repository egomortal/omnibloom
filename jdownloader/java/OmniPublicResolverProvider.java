// SPDX-License-Identifier: GPL-3.0-or-later
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

/**
 * Egress policy omni-public-only-v1 (audit JD-03), JVM-wide layer: every host name lookup in the
 * Java worker goes through this resolver (registered in META-INF/services). A name whose answers
 * include any local, private or console-LAN address is refused outright (DNS rebinding and
 * "public name, private answer" tricks), so code that skips JDownloader's proxy still can't reach
 * the LAN by name. Literal addresses never reach a resolver; the guard proxy and the socket
 * layers in OmniEgressPolicy handle those.
 *
 * "localhost" and the console's own host name answer loopback only, as a hosts file would
 * (InetAddress.getLocalHost() keeps working without disclosing or reaching the LAN address).
 * The connection layers still refuse loopback for JDownloader's traffic.
 */
public final class OmniPublicResolverProvider extends InetAddressResolverProvider {
    public static final String POLICY = OmniPublicAddress.POLICY;
    private static volatile boolean installed;
    /**
     * PC tests only: answers to use instead of the system resolver (there is no other way to get private DNS
     * answers on demand; the JDK ignores resolver providers when jdk.net.hosts.file is set). Whatever it answers is
     * still filtered exactly like a real DNS answer, so setting it can never widen the policy.
     */
    static volatile InetAddressResolver upstreamForTests;
    private static volatile InetAddressResolver builtin;

    public OmniPublicResolverProvider() { }

    /** True once the JVM has taken this provider as its resolver. */
    public static boolean installed() { return installed; }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        String local = null;
        try { local = configuration.lookupLocalHostName(); } catch (Throwable ignored) { }
        builtin = configuration.builtinResolver();
        Filter filter = new Filter(builtin, local);
        installed = true;
        return filter;
    }

    @Override
    public String name() { return POLICY; }

    /**
     * The unfiltered system resolver (or the test upstream), for the guard proxy: it applies its own check to the
     * raw answers, independently of this filter, and never reads InetAddress's cache. null before installation.
     */
    static InetAddressResolver upstream() {
        InetAddressResolver test = upstreamForTests;
        return test != null ? test : builtin;
    }

    static UnknownHostException refused(String host, String why) {
        return new UnknownHostException(POLICY + ": " + why + " (" + (host == null ? "" : host.length() > 80 ? host.substring(0, 80) : host) + ")");
    }

    static final class Filter implements InetAddressResolver {
        private final InetAddressResolver builtin;
        private final String localName;

        Filter(InetAddressResolver builtin, String localName) {
            this.builtin = builtin;
            this.localName = localName == null ? null : normal(localName);
        }

        private static String normal(String host) {
            String h = host.toLowerCase(Locale.ROOT);
            return h.endsWith(".") ? h.substring(0, h.length() - 1) : h;
        }

        private static Stream<InetAddress> loopback(String host, LookupPolicy policy) throws UnknownHostException {
            int c = policy.characteristics();
            boolean v4 = (c & LookupPolicy.IPV4) != 0, v6 = (c & LookupPolicy.IPV6) != 0;
            InetAddress a4 = InetAddress.getByAddress(host, new byte[]{127, 0, 0, 1});
            InetAddress a6 = InetAddress.getByAddress(host, new byte[]{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1});
            List<InetAddress> out = new ArrayList<>(2);
            if ((c & LookupPolicy.IPV6_FIRST) != 0) { if (v6) out.add(a6); if (v4) out.add(a4); }
            else { if (v4) out.add(a4); if (v6) out.add(a6); }
            return out.stream();
        }

        @Override
        public Stream<InetAddress> lookupByName(String host, LookupPolicy policy) throws UnknownHostException {
            if (host == null || host.isEmpty()) throw refused(host, "empty host name");
            String name = normal(host);
            if (name.equals("localhost") || name.endsWith(".localhost") || name.equals(localName)) return loopback(host, policy);
            // RFC 6761: .invalid never resolves; answer here so self-tests and refusals cause no DNS traffic.
            if (name.equals("invalid") || name.endsWith(".invalid")) throw refused(host, "reserved name");
            if (OmniPublicAddress.numericLooking(name)) throw refused(host, "numeric host name");
            List<InetAddress> found = new ArrayList<>();
            InetAddressResolver upstream = upstreamForTests;
            (upstream != null ? upstream : builtin).lookupByName(host, policy).forEach(found::add);
            if (found.isEmpty()) throw new UnknownHostException(host);
            for (InetAddress a : found) {
                if (!OmniPublicAddress.isPublic(a)) throw refused(host, "name resolves to a local or private address");
            }
            return found.stream();
        }

        @Override
        public String lookupByAddress(byte[] addr) throws UnknownHostException {
            return builtin.lookupByAddress(addr);
        }
    }
}
