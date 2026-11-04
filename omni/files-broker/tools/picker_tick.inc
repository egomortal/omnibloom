// OMNI_FILES_BROKER_V1: finishes broker copy jobs on the main thread, and the files self-test
// (native title only, /data/omni/native/files-selftest.flag): starts the broker, lists its places
// through the picker, copies one USB file in and compares it; with no drive it checks that the broker
// refuses everything outside /mnt/usb*, /mnt/ext*. Then Omni exits normally (never killed).
static bool omniOfbSelfTestDone = false;
static void omniOfbSelfTestFinish(bool pass, const std::string& what)
{
    log(("FILES SELFTEST " + std::string(pass ? "PASS" : "FAIL") + ": " + what).c_str());
    omniOfbCleanUploads(0);
    omniPick = OmniPick();
    running = false;
}
static bool omniOfbRefusalsOk(std::string& detail)
{
    std::string sink;
    const int hello = omniOfbCall("hello", "", "", nullptr, 0, &sink);
    const int user = omniOfbCall("list", "/user/home", "", nullptr, 0, &sink);
    const int dots = omniOfbCall("list", "/mnt/usb0/../../user", "", nullptr, 0, &sink);
    const int data = omniOfbCall("read", "/data/omni/native/broker.token", "0\t32", nullptr, 0, &sink);
    const int sysd = omniOfbCall("list", "/system_data/priv", "", nullptr, 0, &sink);
    detail = "hello=" + std::to_string(hello) + " /user=" + std::to_string(user) + " dotdot=" + std::to_string(dots)
        + " /data=" + std::to_string(data) + " /system_data=" + std::to_string(sysd);
    return hello == 0 && user == EACCES && dots == EACCES && data == EACCES && sysd == EACCES;
}
static void omniOfbSelfTestTick()
{
    static const uint32_t start = SDL_GetTicks();
    if (omniOfbSelfTestDone || !omniNativeTitle() || SDL_GetTicks() - start < 8000) return;
    omniOfbSelfTestDone = true;
    if (access("/data/omni/native/files-selftest.flag", F_OK)) return;
    if (omniPick.listener) { log("FILES SELFTEST: a picker is open, skipped"); return; }
    log("FILES SELFTEST: start (OMNI_FILES_BROKER_V1)");
    omniPick = OmniPick();
    const auto places = omniPickPlaces();   // the picker's own path: starts the broker on first use
    std::vector<OmniPickPlace> usb;
    for (auto& p : places) {
        log(("FILES SELFTEST: place " + p.label + " = " + p.path).c_str());
        if (omniOfbRemote(p.path)) usb.push_back(p);
    }
    std::string refusals;
    const bool refuse = omniOfbRefusalsOk(refusals);
    log(("FILES SELFTEST: refusals " + refusals + (refuse ? " (ok)" : " (WRONG)")).c_str());
    if (usb.empty()) { omniOfbSelfTestFinish(refuse, "no USB drive; broker up and refusing everything outside the USB roots: " + refusals); return; }
    omniPickGo(usb[0].path, usb[0].path);   // the picker's directory scan through the broker
    std::string pick;
    long long size = 0;
    for (auto& e : omniPick.entries)
        if (!e.dir && e.size > 0 && e.size <= (64LL << 20)) { pick = usb[0].path + "/" + e.name; size = e.size; break; }
    log(("FILES SELFTEST: " + usb[0].path + " lists " + std::to_string(omniPick.entries.size()) + " entries").c_str());
    if (pick.empty()) { omniOfbSelfTestFinish(refuse, "listed " + usb[0].path + " (" + std::to_string(omniPick.entries.size()) + " entries) but found no file up to 64 MB to copy; " + refusals); return; }
    log(("FILES SELFTEST: copying " + pick + " (" + std::to_string(size) + " bytes)").c_str());
    mkdir(omniData("uploads").c_str(), 0777);
    omniOfbStart(3, [pick, size, refuse]() {
        const std::string dest = omniData("uploads/") + "selftest-" + omniSafeFileName(omniOfbBaseName(pick));
        const int err = omniOfbCopyIn(pick, dest);
        if (err) { omniOfbJob.error = "copy failed: " + omniOfbErr(err); omniOfbJob.state = 3; return; }
        struct stat st {};
        stat(dest.c_str(), &st);
        std::string head;
        const long long n = std::min<long long>(4096, size);
        const int rerr = omniOfbCall("read", pick, "0\t" + std::to_string(n), nullptr, 0, &head);
        std::string local(size_t(n), '\0');
        if (FILE* f = fopen(dest.c_str(), "rb")) { local.resize(fread(&local[0], 1, size_t(n), f)); fclose(f); }
        const bool same = !rerr && head == local && (long long)st.st_size == size;
        omniOfbJob.results = { dest, std::to_string(st.st_size), same ? "match" : "MISMATCH", refuse ? "refusals ok" : "refusals WRONG" };
        omniOfbJob.state = (same && refuse) ? 2 : 3;
        if (!same) omniOfbJob.error = "copied file differs (size " + std::to_string(st.st_size) + " of " + std::to_string(size) + ")";
        else if (!refuse) omniOfbJob.error = "refusals wrong";
    });
}
static void omniOfbTick()
{
    omniOfbSelfTestTick();
    const int st = omniOfbJob.state.load();
    if (st == 1) {
        const long long total = omniOfbJob.total.load(), done = omniOfbJob.done.load();
        if (omniOfbJob.kind != 3 && total > (8LL << 20) && SDL_GetTicks() - omniOfbJob.lastNotice > 1000) {
            omniOfbJob.lastNotice = SDL_GetTicks();
            notice(std::string(omniOfbJob.kind == 1 ? "Copying from the USB drive: " : "Copying to the USB drive: ") + std::to_string(int(100.0 * done / total)) + "%");
        }
        return;
    }
    if (st != 2 && st != 3) return;
    if (omniOfbThread.joinable()) omniOfbThread.join();
    const int kind = omniOfbJob.kind;
    const auto results = omniOfbJob.results;
    const std::string error = omniOfbJob.error;
    omniOfbJob.state = 0;
    if (kind == 1) {
        omniPick.copying = false;
        const bool tabGone = !omniTabAlive(omniPick.tab) || omniPick.tab != active();
        if (st == 3) { notice(error); omniPickFinish({}); }
        else if (tabGone) { notice("Upload cancelled: the tab changed"); omniPickFinish({}); }
        else omniPickFinish(results);
    } else if (kind == 2) {
        notice(st == 2 ? "Copied to " + results[0] : error);
    } else if (kind == 3) {
        std::string what = st == 2 ? "copied " + results[0] + " (" + results[1] + " bytes, " + results[2] + ", " + results[3] + ")" : error;
        omniOfbSelfTestFinish(st == 2, what);
    }
}
