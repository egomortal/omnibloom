import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.appwork.utils.event.queue.QueueAction;
import org.appwork.storage.JSonStorage;
import org.appwork.storage.TypeRef;
import org.appwork.storage.config.JsonConfig;
import org.jdownloader.api.myjdownloader.MyJDownloaderSettings;
import org.jdownloader.settings.GeneralSettings;
import org.jdownloader.api.linkcollector.v2.*;
import org.jdownloader.api.downloads.v2.*;
import jd.controlling.downloadcontroller.DownloadWatchDog;

/** Experimental local bridge to actual JD APIs. No PS5 operations or cloud API.
 *  Egress policy omni-public-only-v1 (audit JD-03): see OmniEgressPolicy. JDownloader is only started when every
 *  layer is installed, and health reports egress_policy only while every layer still holds. */
public final class OmniJDownloaderBridge {
    private static final int MAX_REQUEST = 8192, MAX_RESPONSE = 65536, MAX_LINKS = 64;
    private final byte[] token;
    private final Path downloads;
    private final ServerSocket server;
    private final Map<String, Job> jobs = new LinkedHashMap<>();
    private LinkCollectorAPIImplV2 crawler;
    private DownloadsAPIV2Impl downloader;
    private volatile boolean shutdown;
    private final long deadline;
    private final long idleNanos;
    private volatile long lastActivity = System.nanoTime();
    private final String session, installId;
    private final long nativePid;
    private volatile String startupFailure = "";
    private volatile boolean draining;
    private final AtomicInteger diagnosticErrors = new AtomicInteger();
    private final Path diagnosticRoot;
    private final OmniEgressPolicy egress;
    private final String egressFailure;

    private static String identity(Map<String,Object> config, String name, String pattern) {
        Object value = config.get(name);
        if (!(value instanceof String) || !((String)value).matches(pattern)) throw new IllegalArgumentException("Invalid " + name);
        return (String)value;
    }

    private boolean shouldContinue() {
        long now = System.nanoTime();
        if (now >= deadline || now-lastActivity >= idleNanos) draining = true;
        // Parent owns cancellation/release. A time limit never truncates a download.
        synchronized (this) { return !draining || !jobs.isEmpty(); }
    }

    private static final class Job {
        final String id, url;
        final long created = System.nanoTime();
        long crawlId;
        long[] links = new long[0];
        boolean moving, started, cancelled;
        int releasePhase;
        AtomicBoolean releaseFence;
        String state = "extracting", error = "", title = "Inspecting link", filepath = "";
        Job(String id, String url) { this.id = id; this.url = url; }
    }

    static Map<String, Object> object(Object... fields) {
        Map<String, Object> value = new LinkedHashMap<>();
        for (int i = 0; i < fields.length; i += 2) value.put((String) fields[i], fields[i+1]);
        return value;
    }

    private OmniJDownloaderBridge(Map<String, Object> config, OmniEgressPolicy egress, String egressFailure) throws Exception {
        this.egress = egress;
        this.egressFailure = egressFailure == null ? "" : egressFailure;
        String secret = (String) config.get("token");
        if (secret == null || !secret.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("Invalid session token");
        token = secret.getBytes(StandardCharsets.US_ASCII);
        session = identity(config, "session", "[0-9a-f]{32}");
        installId = identity(config, "install_id", "[A-Za-z0-9._-]{1,128}");
        String suppliedPid = System.getProperty("omni.jd.nativePid");
        nativePid = suppliedPid == null ? ProcessHandle.current().pid() : Long.parseLong(suppliedPid);
        if (nativePid <= 0) throw new IllegalArgumentException("Invalid native PID");
        downloads = Paths.get((String) config.get("downloads")).toAbsolutePath().normalize();
        Files.createDirectories(downloads);
        if (Files.isSymbolicLink(downloads)) throw new IllegalArgumentException("Downloads root must not be a symlink");
        int seconds = ((Number) config.get("max_seconds")).intValue();
        if (seconds < 5 || seconds > 86400) throw new IllegalArgumentException("Lifetime must be 5..86400 seconds");
        Object idleValue = config.get("idle_seconds");
        int idleSeconds = idleValue == null ? 300 : ((Number)idleValue).intValue();
        if (idleSeconds < 60 || idleSeconds > 3600) throw new IllegalArgumentException("Idle lifetime must be 60..3600 seconds");
        idleNanos = TimeUnit.SECONDS.toNanos(idleSeconds);
        deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(seconds);
        server = new ServerSocket();
        server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), ((Number) config.get("port")).intValue()), 8);
        server.setSoTimeout(1000);
        Path ready = Paths.get((String) config.get("ready_file"));
        diagnosticRoot = ready.toAbsolutePath().normalize().getParent();
        byte[] data = JSonStorage.serializeToJsonByteArray(object("host", "127.0.0.1", "port", server.getLocalPort(), "token", secret,
            "protocol", 2, "target_tested", false, "session", session, "install_id", installId, "native_pid", nativePid));
        Files.write(ready, data, StandardOpenOption.CREATE_NEW);
    }

    private static byte[] read(Socket socket, int length, long deadline) throws IOException {
        byte[] data = new byte[length];
        int at = 0;
        InputStream input = socket.getInputStream();
        while (at < length) {
            long left = TimeUnit.NANOSECONDS.toMillis(deadline - System.nanoTime());
            if (left <= 0) throw new SocketTimeoutException("Request deadline");
            socket.setSoTimeout((int) Math.max(1, left));
            int count = input.read(data, at, length-at);
            if (count < 0) throw new EOFException("Incomplete request");
            at += count;
        }
        return data;
    }

    private void handle(Socket socket) {
        String phase = "readprefix";
        try (Socket owned = socket) {
            long limit = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
            byte[] prefix = read(owned, 4, limit);
            int length = java.nio.ByteBuffer.wrap(prefix).getInt();
            if (length < 1 || length > MAX_REQUEST) return; // HTTP is not this binary protocol.
            phase = "readbody";
            byte[] payload = read(owned, length, limit);
            phase = "json";
            Map<String, Object> request = JSonStorage.restoreFromString(new String(payload, StandardCharsets.UTF_8), TypeRef.HASHMAP);
            phase = "command";
            Map<String, Object> result;
            Object received = request.get("token");
            if (!(received instanceof String) || !MessageDigest.isEqual(token, ((String) received).getBytes(StandardCharsets.UTF_8))) {
                result = object("ok", false, "error", "Forbidden");
            } else {
                try { result = command(request); }
                catch (Exception error) { result = object("ok", false, "error", error.getClass().getSimpleName() + ": " + safe(error.getMessage())); }
            }
            phase = "serialize";
            byte[] body = JSonStorage.serializeToJsonByteArray(result);
            if (body.length > MAX_RESPONSE) body = JSonStorage.serializeToJsonByteArray(object("ok", false, "error", "Response exceeds limit"));
            phase = "write";
            DataOutputStream output = new DataOutputStream(owned.getOutputStream());
            output.writeInt(body.length); output.write(body); output.flush();
        } catch (Throwable failure) { diagnostic(phase, failure); }
    }

    private static String diagnosticName(String value, int maximum) {
        if (value == null) return "unknown";
        StringBuilder result = new StringBuilder(Math.min(maximum, value.length()));
        for (int i = 0; i < value.length() && i < maximum; i++) {
            char c = value.charAt(i);
            result.append(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9'
                || c == '_' || c == '$' || c == '.' || c == '<' || c == '>' || c == '-' ? c : '_');
        }
        return result.toString();
    }

    private void diagnostic(String phase, Throwable failure) {
        // Independent of command()/the bridge monitor and AppWork JSON. Never
        // serialize messages, request bytes, URLs, tokens, filenames or paths.
        int sequence = diagnosticErrors.getAndIncrement();
        if (sequence < 0 || sequence >= 8) return;
        try {
            StringBuilder value = new StringBuilder(2048);
            value.append("{\"schema\":\"omni-jd-bridge-diagnostic/v1\",\"session\":\"").append(session)
                .append("\",\"install_id\":\"").append(installId).append("\",\"native_pid\":").append(nativePid)
                .append(",\"sequence\":").append(sequence + 1).append(",\"phase\":\"")
                .append(diagnosticName(phase, 16)).append("\",\"errors\":[");
            Throwable error = failure;
            for (int cause = 0; error != null && cause < 4; cause++) {
                if (cause > 0) value.append(',');
                value.append("{\"class\":\"").append(diagnosticName(error.getClass().getName(), 160)).append("\",\"frames\":[");
                StackTraceElement[] frames = error.getStackTrace();
                for (int i = 0; i < frames.length && i < 12; i++) {
                    if (i > 0) value.append(',');
                    value.append("{\"class\":\"").append(diagnosticName(frames[i].getClassName(), 160))
                        .append("\",\"method\":\"").append(diagnosticName(frames[i].getMethodName(), 96))
                        .append("\",\"line\":").append(frames[i].getLineNumber()).append('}');
                }
                value.append("]}");
                Throwable next = error.getCause();
                if (next == error || next == failure) break;
                error = next;
            }
            value.append("]}\n");
            byte[] bytes = value.toString().getBytes(StandardCharsets.UTF_8);
            if (bytes.length > 24576 || Files.isSymbolicLink(diagnosticRoot)) return;
            Path path = diagnosticRoot.resolve("diagnostic-error-" + (sequence + 1) + ".json");
            try (java.nio.channels.FileChannel output = java.nio.channels.FileChannel.open(path,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
                java.nio.ByteBuffer buffer = java.nio.ByteBuffer.wrap(bytes);
                while (buffer.hasRemaining()) output.write(buffer);
                output.force(true);
            }
        } catch (Throwable ignored) {
            // Diagnostics are best effort under heap/filesystem failure. Never
            // recurse into another logger or replace existing owned evidence.
        }
    }

    private Map<String, Object> egressStatus() {
        if (egress != null) return egress.status(ready());
        return object("policy", null, "guard", false, "problem", egressFailure);
    }

    private static String safe(String value) { return value == null ? "Operation failed" : value.substring(0, Math.min(250, value.length())); }
    private boolean ready() { return jd.SecondLevelLaunch.INIT_COMPLETE.isReached(); }
    private static boolean terminal(Job job) { return Arrays.asList("completed", "failed", "cancelled").contains(job.state); }

    static List<Path> validateCompletedOutputs(Path directory, List<Path> candidates, int expected) throws IOException {
        if (expected < 1 || expected > MAX_LINKS || candidates.size() != expected || Files.isSymbolicLink(directory)) throw new IOException("Invalid output set");
        Path root = directory.toRealPath();
        List<Path> verified = new ArrayList<>();
        for (Path candidate : candidates) {
            if (candidate == null || !Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Missing output file");
            Path real = candidate.toRealPath();
            if (!real.startsWith(root)) throw new IOException("Output escaped its owned directory");
            verified.add(real);
        }
        return verified;
    }

    // Both controller APIs enqueue their mutations. A low-priority collector
    // fence followed by a download fence settles moves and removals in order.
    private static AtomicBoolean controllerFence() {
        AtomicBoolean completed = new AtomicBoolean();
        jd.controlling.linkcollector.LinkCollector.getInstance().getQueue().addAsynch(new QueueAction<Void, RuntimeException>(org.appwork.utils.event.queue.Queue.QueuePriority.LOW) {
            protected Void run() {
                jd.controlling.downloadcontroller.DownloadController.getInstance().getQueue().addAsynch(new QueueAction<Void, RuntimeException>(org.appwork.utils.event.queue.Queue.QueuePriority.LOW) {
                    protected Void run() { completed.set(true); return null; }
                });
                return null;
            }
        });
        return completed;
    }

    private List<CrawledLinkAPIStorableV2> crawled(Job job) throws Exception {
        CrawledLinkQueryStorable query = new CrawledLinkQueryStorable();
        query.setJobUUIDs(new long[]{job.crawlId}); query.setMaxResults(MAX_LINKS+1);
        return crawler.queryLinks(query);
    }

    private synchronized Map<String, Object> command(Map<String, Object> request) throws Exception {
        String action = (String) request.get("action");
        Object suppliedSession = request.get("session");
        if (!(suppliedSession instanceof String) || !session.equals(suppliedSession)) throw new IllegalArgumentException("Session mismatch");
        lastActivity = System.nanoTime();
        if (lastActivity >= deadline) draining = true;
        if (ready() && crawler == null) { crawler = new LinkCollectorAPIImplV2(); downloader = new DownloadsAPIV2Impl(); }
        if ("health".equals(action)) {
            CrawledLinkQueryStorable cq = new CrawledLinkQueryStorable(); cq.setMaxResults(MAX_LINKS+1);
            LinkQueryStorable dq = new LinkQueryStorable(); dq.setMaxResults(MAX_LINKS+1);
            Map<String, Object> guard = egressStatus();
            return object("ok", true, "ready", ready(), "status", ready() ? "Real JDownloader core ready; target acceptance is external" : "JDownloader is initializing", "jobs", jobs.size(), "target_tested", false,
                "egress_policy", guard.get("policy"), "egress", guard,
                "session", session, "install_id", installId, "native_pid", nativePid,
                "draining", draining, "startup_error", startupFailure,
                "cloud_active", ready() && org.jdownloader.api.myjdownloader.MyJDownloaderController.getInstance().isActive(),
                "legacy_api", JsonConfig.create(org.jdownloader.api.RemoteAPIConfig.class).isDeprecatedApiEnabled(),
                "core_crawled", ready() ? crawler.queryLinks(cq).size() : null,
                "core_downloads", ready() ? downloader.queryLinks(dq).size() : null);
        }
        if ("keepalive".equals(action)) return object("ok", true, "draining", draining);
        if ("shutdown".equals(action)) {
            if (!ready()) throw new IllegalStateException("JDownloader is still initializing");
            CrawledLinkQueryStorable cq = new CrawledLinkQueryStorable(); cq.setMaxResults(1);
            LinkQueryStorable dq = new LinkQueryStorable(); dq.setMaxResults(1);
            if (!jobs.isEmpty() || !crawler.queryLinks(cq).isEmpty() || !downloader.queryLinks(dq).isEmpty()
                || crawler.isCollecting() || DownloadWatchDog.getInstance().isRunning() || DownloadWatchDog.getInstance().isStopping())
                throw new IllegalStateException("Shutdown requires released jobs and a quiescent core");
            shutdown = true; return object("ok", true);
        }
        if (!ready()) throw new IllegalStateException("JDownloader is still initializing");
        String id = (String) request.get("id");
        if (id == null || !id.matches("[0-9a-f]{16}")) throw new IllegalArgumentException("Invalid job ID");
        Job job = jobs.get(id);
        if ("submit".equals(action)) {
            if (draining) throw new IllegalStateException("Runtime lifetime expired; restart after releasing jobs");
            String url = (String) request.get("url");
            URI parsed = new URI(url);
            if (url.length() > 4096 || url.matches(".*[\\s\\\\].*") || parsed.getRawUserInfo() != null || parsed.getHost() == null
                || !("http".equalsIgnoreCase(parsed.getScheme()) || "https".equalsIgnoreCase(parsed.getScheme()))) throw new IllegalArgumentException("Invalid HTTP(S) URL");
            // Fail fast on what the guard would refuse anyway; the guard re-checks every connection JD makes.
            InetAddress literal = OmniPublicAddress.literal(parsed.getHost());
            if ((literal != null && !OmniPublicAddress.isPublic(literal)) || OmniPublicAddress.numericLooking(parsed.getHost()))
                throw new IllegalArgumentException("Local or private address");
            if (job == null && egressStatus().get("policy") == null) throw new IllegalStateException("JDownloader's public-address policy is not active");
            if (job != null) {
                if (!job.url.equals(url)) throw new IllegalArgumentException("Job ID already used for another URL");
                return object("ok", true, "replayed", true);
            }
            if (!jobs.isEmpty()) throw new IllegalStateException("Java worker is busy or awaiting release");
            CrawledLinkQueryStorable existingCrawled = new CrawledLinkQueryStorable(); existingCrawled.setMaxResults(1);
            LinkQueryStorable existingDownloads = new LinkQueryStorable(); existingDownloads.setMaxResults(1);
            if (!crawler.queryLinks(existingCrawled).isEmpty() || !downloader.queryLinks(existingDownloads).isEmpty())
                throw new IllegalStateException("Untracked JDownloader links were restored; use a fresh private runtime state");
            Path destination = downloads.resolve(id);
            Files.createDirectories(destination);
            if (Files.isSymbolicLink(destination)) throw new IllegalArgumentException("Job directory must not be a symlink");
            AddLinksQueryStorable query = new AddLinksQueryStorable();
            query.setLinks(url); query.setPackageName("omni-" + id); query.setDestinationFolder(destination.toString());
            query.setAutostart(false); query.setAutoExtract(false); query.setDeepDecrypt(false); query.setAssignJobID(true);
            job = new Job(id, url);
            job.crawlId = crawler.addLinks(query).getId();
            jobs.put(id, job);
            return object("ok", true, "replayed", false);
        }
        if (job == null) {
            if ("release".equals(action) || "cancel".equals(action)) return object("ok", true);
            throw new IllegalArgumentException("Unknown job");
        }
        if ("cancel".equals(action)) {
            job.cancelled = true;
            crawler.abort(job.crawlId);
            if (job.links.length > 0) downloader.setEnabled(false, job.links, null);
            DownloadWatchDog.getInstance().stopDownloads();
            return object("ok", true);
        }
        if ("release".equals(action)) {
            refresh(job);
            if (!terminal(job)) throw new IllegalStateException("Job is still active");
            if (crawler.isCollecting() || DownloadWatchDog.getInstance().isRunning() || DownloadWatchDog.getInstance().isStopping()) throw new IllegalStateException("Job resources are still active");
            if (job.releasePhase == 0) {
                job.releaseFence = controllerFence(); job.releasePhase = 1;
                throw new IllegalStateException("Job resources are still active: settling moves");
            }
            if (!job.releaseFence.get()) throw new IllegalStateException("Job resources are still active: controller fence");
            if (job.releasePhase == 1) {
                long[] remains = crawled(job).stream().mapToLong(value -> value.getUuid()).toArray();
                if (remains.length > 0) crawler.removeLinks(remains, null);
                if (job.links.length > 0) downloader.removeLinks(job.links, null);
                job.releaseFence = controllerFence(); job.releasePhase = 2;
                throw new IllegalStateException("Job resources are still active: settling removals");
            }
            LinkQueryStorable check = new LinkQueryStorable(); check.setLinkUUIDs(job.links); check.setMaxResults(MAX_LINKS+1);
            if (!crawled(job).isEmpty() || (job.links.length > 0 && !downloader.queryLinks(check).isEmpty())) {
                job.releasePhase = 0;
                throw new IllegalStateException("Job resources are still active: owned core links remain");
            }
            jobs.remove(id);
            return object("ok", true);
        }
        if (!"status".equals(action)) throw new IllegalArgumentException("Unknown action");
        return refresh(job);
    }

    private Map<String, Object> refresh(Job job) throws Exception {
        Long loaded = 0L, total = 0L;
        if (!terminal(job)) {
            if (job.cancelled) {
                if (!crawler.isCollecting() && !DownloadWatchDog.getInstance().isRunning() && !DownloadWatchDog.getInstance().isStopping()) job.state = job.error.isEmpty() ? "cancelled" : "failed";
                return object("ok", true, "state", job.state, "progress", null, "title", job.title, "error", job.error);
            }
            if (job.links.length == 0) {
                CrawledLinkQueryStorable query = new CrawledLinkQueryStorable();
                query.setJobUUIDs(new long[]{job.crawlId}); query.setMaxResults(MAX_LINKS+1); query.setJobUUID(true);
                List<CrawledLinkAPIStorableV2> found = crawler.queryLinks(query);
                if (found.size() > MAX_LINKS) throw new IllegalStateException("Link collection exceeds prototype limit64");
                if (!crawler.isCollecting() && !found.isEmpty() && !job.moving) {
                    job.links = found.stream().mapToLong(value -> value.getUuid()).toArray();
                    crawler.moveToDownloadlist(job.links, null);
                    job.moving = true;
                } else if (!crawler.isCollecting() && found.isEmpty() && System.nanoTime()-job.created > TimeUnit.SECONDS.toNanos(90)) {
                    job.state = "failed"; job.error = "No supported downloadable links were found.";
                }
            }
            if (job.links.length > 0) {
                LinkQueryStorable query = new LinkQueryStorable();
                query.setLinkUUIDs(job.links); query.setMaxResults(MAX_LINKS); query.setBytesLoaded(true); query.setBytesTotal(true);
                query.setFinished(true); query.setRunning(true); query.setSkipped(true); query.setStatus(true);
                List<DownloadLinkAPIStorableV2> found = downloader.queryLinks(query);
                if (!found.isEmpty()) {
                    if (!job.started) { downloader.forceDownload(job.links, null); DownloadWatchDog.getInstance().startDownloads(); job.started = true; }
                    boolean finished = found.size() == job.links.length;
                    boolean skipped = false;
                    List<Path> completedOutputs = new ArrayList<>();
                    for (DownloadLinkAPIStorableV2 link : found) {
                        loaded += link.getBytesLoaded(); total += Math.max(0, link.getBytesTotal());
                        finished &= link.isFinished(); skipped |= link.isSkipped();
                        job.title = link.getName();
                        if (link.isFinished()) {
                            Path candidate = null;
                            PackageQueryStorable packages = new PackageQueryStorable();
                            packages.setPackageUUIDs(new long[]{link.getPackageUUID()}); packages.setSaveTo(true); packages.setMaxResults(1);
                            List<FilePackageAPIStorableV2> parents = downloader.queryPackages(packages);
                            if (!parents.isEmpty() && parents.get(0).getSaveTo() != null) {
                                candidate = Paths.get(parents.get(0).getSaveTo()).resolve(link.getName()).normalize();
                            }
                            completedOutputs.add(candidate);
                        }
                    }
                    job.state = "downloading";
                    if (finished) {
                        try {
                            List<Path> verified = validateCompletedOutputs(downloads.resolve(job.id), completedOutputs, job.links.length);
                            job.filepath = verified.get(verified.size()-1).toString(); job.state = "completed";
                        } catch (IOException invalid) { job.state = "failed"; job.error = "JDownloader output set could not be verified."; }
                    }
                    if (skipped && !finished) { job.state = "processing"; job.error = "JDownloader requires manual action or skipped this link."; job.cancelled = true; DownloadWatchDog.getInstance().stopDownloads(); }
                }
            }
        }
        Object progress = null;
        if ("completed".equals(job.state)) progress = Integer.valueOf(100);
        else if (total > 0) progress = Double.valueOf(Math.min(100, 100.0*loaded/total));
        return object("ok", true, "state", job.state, "title", job.title, "progress", progress, "filepath", job.filepath, "error", job.error);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("Expected one owned configuration file");
        System.setProperty("omni.jd.localOnly", "true");
        System.setProperty("classloader_00000000", "org.jdownloader.update.launcher.ClassLoaderExtensionImpl");
        Class.forName("org.jdownloader.startup.Main");
        // Audit JD-03: every egress layer is in place, and proven, before any JDownloader code can connect.
        OmniEgressPolicy egress = null;
        String egressFailure = "";
        try {
            egress = OmniEgressPolicy.install();
            egress.configureJdownloader();
        } catch (Throwable failure) {
            egress = null;
            egressFailure = "Egress policy unavailable: " + failure.getClass().getSimpleName() + ": " + safe(failure.getMessage());
        }
        JsonConfig.create(org.jdownloader.api.RemoteAPIConfig.class).setHeadlessMyJDownloaderMandatory(false);
        JsonConfig.create(org.jdownloader.api.RemoteAPIConfig.class).setDeprecatedApiEnabled(false);
        JsonConfig.create(org.jdownloader.api.RemoteAPIConfig.class).setExternInterfaceEnabled(false);
        JsonConfig.create(org.jdownloader.api.RemoteAPIConfig.class).setJDAnywhereApiEnabled(false);
        JsonConfig.create(MyJDownloaderSettings.class).setAutoConnectEnabledV2(false);
        GeneralSettings general = JsonConfig.create(GeneralSettings.class);
        general.setMaxSimultaneDownloads(1); general.setMaxChunksPerFile(1); general.setUseAvailableAccounts(false); general.setSaveLinkgrabberListEnabled(false);
        general.setAutoStartDownloadOption(org.jdownloader.settings.AutoDownloadStartOption.NEVER);
        Map<String, Object> config = JSonStorage.restoreFromString(Files.readString(Paths.get(args[0])), TypeRef.HASHMAP);
        OmniJDownloaderBridge bridge = new OmniJDownloaderBridge(config, egress, egressFailure);
        if (egress == null) bridge.startupFailure = egressFailure;     // fail closed: JDownloader is never started
        Thread startup = new Thread(() -> {
            try { org.jdownloader.startup.Main.main(new String[]{"-norestart", "-silent"}); }
            catch (Throwable failure) {
                bridge.diagnostic("startup", failure);
                bridge.startupFailure = failure.getClass().getName() + ": " + safe(failure.getMessage());
            }
        }, "omni-jd-startup");
        startup.setDaemon(true);
        if (egress != null) startup.start();
        ThreadPoolExecutor pool = new ThreadPoolExecutor(4, 4, 0, TimeUnit.SECONDS, new ArrayBlockingQueue<>(8), task -> { Thread t = new Thread(task, "omni-jd-rpc"); t.setDaemon(true); return t; });
        try {
            while (!bridge.shutdown && bridge.shouldContinue()) {
                try {
                    Socket socket = bridge.server.accept();
                    try { pool.execute(() -> bridge.handle(socket)); }
                    catch (RejectedExecutionException busy) { socket.close(); }
                } catch (SocketTimeoutException idle) { }
            }
        } finally {
            bridge.server.close(); pool.shutdownNow();
            DownloadWatchDog.getInstance().stopDownloads();
            System.exit(0);
        }
    }
}
