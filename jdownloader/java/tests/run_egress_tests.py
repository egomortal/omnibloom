# SPDX-License-Identifier: GPL-3.0-or-later
"""PC tests for the JDownloader egress policy omni-public-only-v1 (audit JD-03).

    python jdownloader/java/tests/run_egress_tests.py --jd "<your JDownloader 2 folder>" --out <scratch dir> [--online]

Compiles the bridge classes against your own JDownloader 2 jars (read only, never copied into the repo),
then runs each test mode in its own JVM (the layers are JVM-wide). Writes <out>/egress-test-receipt.json.
Needs a JDK 21+ (javac/java on PATH or --jdk).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
JAVA = os.path.dirname(HERE)
SOURCES = ["OmniPublicAddress.java", "OmniPublicResolverProvider.java", "OmniEgressPolicy.java",
           "OmniJDownloaderBridge.java", os.path.join("upstream-adapted", "org", "jdownloader", "api", "myjdownloader",
                                                      "MyJDownloaderController.java")]
SERVICE = os.path.join("META-INF", "services", "java.net.spi.InetAddressResolverProvider")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tool(jdk, name):
    if jdk:
        return os.path.join(jdk, "bin", name)
    return shutil.which(name) or name


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jd", required=True, help="your JDownloader 2 folder (Core.jar, JDownloader.jar, libs/)")
    p.add_argument("--out", required=True)
    p.add_argument("--jdk")
    p.add_argument("--online", action="store_true", help="also check that public sites work (needs internet)")
    a = p.parse_args()
    out = os.path.abspath(a.out)
    classes = os.path.join(out, "classes")
    tests = os.path.join(out, "test-classes")
    for d in (classes, tests):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    jd_cp = os.pathsep.join([os.path.join(a.jd, "Core.jar"), os.path.join(a.jd, "JDownloader.jar"), os.path.join(a.jd, "libs", "*")])
    javac, java = tool(a.jdk, "javac"), tool(a.jdk, "java")
    srcs = [os.path.join(JAVA, s) for s in SOURCES]
    subprocess.run([javac, "--release", "21", "-encoding", "UTF-8", "-Xlint:all,-path,-deprecation", "-cp", jd_cp, "-d", classes] + srcs, check=True)
    os.makedirs(os.path.dirname(os.path.join(classes, SERVICE)))
    shutil.copyfile(os.path.join(JAVA, SERVICE), os.path.join(classes, SERVICE))
    subprocess.run([javac, "--release", "21", "-encoding", "UTF-8", "-cp", classes + os.pathsep + jd_cp, "-d", tests,
                    os.path.join(HERE, "EgressPolicyTests.java")], check=True)
    cp = classes + os.pathsep + tests + os.pathsep + jd_cp
    modes = ["unit", "prod", "redirect"] + (["online"] if a.online else [])
    results = {}
    for mode in modes:
        props = ["-Djava.awt.headless=true", "-Dsun.net.inetaddr.ttl=0", "-Dsun.net.inetaddr.negative.ttl=0"]
        started = time.time()
        run = subprocess.run([java] + props + ["-cp", cp, "EgressPolicyTests", mode], capture_output=True, text=True, timeout=300)
        lines = run.stdout.splitlines()
        sys.stdout.write(run.stdout)
        if run.returncode and run.stderr:
            sys.stdout.write(run.stderr[-4000:])
        results[mode] = {"exit_code": run.returncode, "seconds": round(time.time() - started, 1),
                         "passed": sum(1 for l in lines if l.startswith("PASS ")),
                         "failed": [l[5:] for l in lines if l.startswith("FAIL ")]}
    version = subprocess.run([java, "-version"], capture_output=True, text=True).stderr.splitlines()[0]
    build_json = os.path.join(a.jd, "build.json")
    jd_revision = None
    if os.path.exists(build_json):
        try:
            jd_revision = json.load(open(build_json, encoding="utf-8")).get("JDownloaderRevision")
        except ValueError:
            pass
    receipt = {
        "schema": "omni-jd-egress-test/v1", "policy": "omni-public-only-v1",
        "passed": all(r["exit_code"] == 0 for r in results.values()), "modes": results,
        "java": version, "jd_revision": jd_revision, "online": a.online,
        "sources": {s.replace(os.sep, "/"): sha(os.path.join(JAVA, s)) for s in SOURCES + [SERVICE]},
        "tests": {"EgressPolicyTests.java": sha(os.path.join(HERE, "EgressPolicyTests.java"))},
        "classes": {os.path.relpath(os.path.join(d, f), classes).replace(os.sep, "/"): sha(os.path.join(d, f))
                    for d, _, fs in os.walk(classes) for f in sorted(fs)},
        "console_contacted": False, "target_tested": False,
    }
    with open(os.path.join(out, "egress-test-receipt.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(receipt, f, indent=1, sort_keys=True)
        f.write("\n")
    print("RECEIPT", os.path.join(out, "egress-test-receipt.json"), "passed" if receipt["passed"] else "FAILED")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
