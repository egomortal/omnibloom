// SPDX-License-Identifier: GPL-3.0-or-later
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;

/**
 * Egress policy omni-public-only-v1 (audit JD-03): which addresses JDownloader may reach.
 *
 * Same rule as downloader-7's probe.public_address (yt-dlp): public unicast only. Refused:
 * loopback, private, link-local, shared/CGNAT (100.64/10), multicast, reserved, unspecified,
 * documentation and benchmark ranges, IPv6 outside global unicast (2000::/3), Teredo, 6to4,
 * ULA and site-local. IPv4-mapped IPv6 is checked as IPv4. On top of that, every subnet the
 * console itself is on is refused (its own LAN, even when that LAN uses public addresses,
 * which is common for IPv6 /64s).
 *
 * No JDownloader classes: the JVM-wide resolver uses this before JDownloader is loaded.
 */
public final class OmniPublicAddress {
    public static final String POLICY = "omni-public-only-v1";

    // {network, prefix length} for refused IPv4 ranges.
    private static final int[][] REFUSED_V4 = {
        {ip(0, 0, 0, 0), 8}, {ip(10, 0, 0, 0), 8}, {ip(100, 64, 0, 0), 10}, {ip(127, 0, 0, 0), 8},
        {ip(169, 254, 0, 0), 16}, {ip(172, 16, 0, 0), 12}, {ip(192, 0, 0, 0), 24}, {ip(192, 0, 2, 0), 24},
        {ip(192, 88, 99, 0), 24}, {ip(192, 168, 0, 0), 16}, {ip(198, 18, 0, 0), 15}, {ip(198, 51, 100, 0), 24},
        {ip(203, 0, 113, 0), 24}, {ip(224, 0, 0, 0), 4}, {ip(240, 0, 0, 0), 4},
    };
    private static final long LAN_REFRESH_NANOS = 30_000_000_000L;
    private static volatile List<byte[][]> lan = Collections.emptyList();   // {address, mask}
    private static volatile long lanAt;
    private static volatile int lanCount = -1;

    private OmniPublicAddress() { }

    private static int ip(int a, int b, int c, int d) { return a << 24 | b << 16 | c << 8 | d; }

    /** The address bytes to judge: IPv4-mapped IPv6 becomes IPv4; scope IDs are ignored. */
    static byte[] canonical(InetAddress address) {
        byte[] b = address.getAddress();
        if (b.length == 16) {
            boolean mapped = b[10] == (byte) 0xff && b[11] == (byte) 0xff;
            for (int i = 0; i < 10 && mapped; i++) mapped = b[i] == 0;
            if (mapped) return new byte[]{b[12], b[13], b[14], b[15]};
        }
        return b;
    }

    /** True only for a public unicast address outside the console's own subnets. */
    public static boolean isPublic(InetAddress address) {
        if (address == null) return false;
        byte[] b = canonical(address);
        if (!(b.length == 4 ? publicV4(b) : b.length == 16 && publicV6(b))) return false;
        return !onConsoleLan(b);
    }

    static boolean publicV4(byte[] b) {
        int x = (b[0] & 0xff) << 24 | (b[1] & 0xff) << 16 | (b[2] & 0xff) << 8 | (b[3] & 0xff);
        for (int[] range : REFUSED_V4) {
            int mask = range[1] == 0 ? 0 : -1 << (32 - range[1]);
            if ((x & mask) == range[0]) return false;
        }
        return true;
    }

    static boolean publicV6(byte[] b) {
        int b0 = b[0] & 0xff, b1 = b[1] & 0xff, b2 = b[2] & 0xff;
        if ((b0 & 0xe0) != 0x20) return false;                         // only 2000::/3 is global unicast
        if (b0 == 0x20 && b1 == 0x01 && (b2 & 0xfe) == 0x00) return false;   // 2001::/23 (Teredo, ORCHID, ...)
        if (b0 == 0x20 && b1 == 0x01 && b2 == 0x0d && (b[3] & 0xff) == 0xb8) return false;   // 2001:db8::/32
        if (b0 == 0x20 && b1 == 0x02) return false;                    // 2002::/16 6to4
        if (b0 == 0x3f && b1 == 0xff && (b2 & 0xf0) == 0x00) return false;   // 3fff::/20 documentation
        return true;
    }

    /** The console's own subnets (refreshed every 30 s). An unreadable interface list leaves the range rules. */
    static boolean onConsoleLan(byte[] b) {
        long now = System.nanoTime();
        if (lanCount < 0 || now - lanAt > LAN_REFRESH_NANOS) refreshLan(now);
        for (byte[][] net : lan) {
            byte[] address = net[0], mask = net[1];
            if (address.length != b.length) continue;
            boolean same = true;
            for (int i = 0; i < b.length && same; i++) same = ((b[i] ^ address[i]) & mask[i]) == 0;
            if (same) return true;
        }
        return false;
    }

    private static synchronized void refreshLan(long now) {
        if (lanCount >= 0 && now - lanAt <= LAN_REFRESH_NANOS) return;
        List<byte[][]> found = new ArrayList<>();
        try {
            Enumeration<NetworkInterface> all = NetworkInterface.getNetworkInterfaces();
            while (all != null && all.hasMoreElements()) {
                NetworkInterface nif = all.nextElement();
                for (InterfaceAddress ia : nif.getInterfaceAddresses()) {
                    InetAddress a = ia.getAddress();
                    if (a == null) continue;
                    byte[] raw = canonical(a);
                    int bits = raw.length * 8;
                    int prefix = ia.getNetworkPrefixLength();
                    // A missing or implausible prefix still refuses the console's own address.
                    int minimum = raw.length == 4 ? 8 : 32;
                    if (prefix < minimum || prefix > bits) prefix = bits;
                    byte[] mask = new byte[raw.length];
                    for (int i = 0; i < raw.length; i++) {
                        int left = Math.max(0, Math.min(8, prefix - i * 8));
                        mask[i] = (byte) (left == 0 ? 0 : 0xff << (8 - left));
                    }
                    found.add(new byte[][]{raw, mask});
                }
            }
        } catch (Throwable unreadable) {
            // Keep the previous list; the fixed range rules still apply.
            if (lanCount >= 0) { lanAt = now; return; }
        }
        lan = Collections.unmodifiableList(found);
        lanCount = found.size();
        lanAt = now;
    }

    /** How many console subnets are refused on top of the fixed ranges (-1 before the first read). */
    public static int consoleSubnets() { if (lanCount < 0) refreshLan(System.nanoTime()); return lanCount; }

    /** Address literal (IPv4 dotted quad or bracket-free IPv6), parsed without any name lookup; else null. */
    public static InetAddress literal(String host) {
        if (host == null || host.isEmpty() || host.length() > 64) return null;
        String h = host.startsWith("[") && host.endsWith("]") ? host.substring(1, host.length() - 1) : host;
        try {
            if (h.indexOf(':') >= 0) {
                // Hex digits, ':' and '.' only (no scope IDs): Java then parses it as a literal or throws; never a lookup.
                if (!h.matches("[0-9A-Fa-f:.]+")) return null;
                return InetAddress.getByName(h);
            }
            if (h.matches("[0-9]{1,3}(\\.[0-9]{1,3}){3}")) {
                String[] parts = h.split("\\.");
                byte[] raw = new byte[4];
                for (int i = 0; i < 4; i++) {
                    int v = Integer.parseInt(parts[i]);
                    if (v > 255) return null;
                    raw[i] = (byte) v;
                }
                return InetAddress.getByAddress(h, raw);
            }
        } catch (Exception notLiteral) {
            return null;
        }
        return null;
    }

    /**
     * Hosts that only look like names but are numbers (inet_aton forms such as 2130706433, 0x7f.1, 127.1).
     * Java's own parser refuses them, but a C library or another stack might not; the guard refuses them.
     */
    public static boolean numericLooking(String host) {
        if (host == null) return false;
        String h = host.endsWith(".") ? host.substring(0, host.length() - 1) : host;
        return h.matches("(0[xX][0-9A-Fa-f]+|[0-9]+)(\\.(0[xX][0-9A-Fa-f]+|[0-9]+)){0,3}");
    }
}
