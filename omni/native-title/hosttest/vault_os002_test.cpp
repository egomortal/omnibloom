// SPDX-License-Identifier: GPL-3.0-or-later
// OS-002 regression tests for OMNI_VAULT_V2 (OmniVault.h): the vault, its key and the old XOR store are never
// overwritten, replaced or retired when they exist but can't be read. Fails on the s3 OmniVault.h, passes on s3.1.
// Build: g++ -std=c++17 -fsanitize=address,undefined -I../engine-patches/entry vault_os002_test.cpp -lcrypto
#include "OmniVault.h"
#include <dirent.h>
using namespace OmniVault;
static int fails = 0, passes = 0;
#define CHECK(c) do { if (c) ++passes; else { ++fails; fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); } } while (0)
static std::string mkdir_tmp() { char t[] = "/tmp/vault-os002-XXXXXX"; return std::string(mkdtemp(t)) + "/"; }
static void rmrf(const std::string& d) { std::string c = "chmod -R u+rwx '" + d + "' 2>/dev/null; rm -rf '" + d + "'"; (void)!system(c.c_str()); }
static std::string slurp(const std::string& p) { std::string s; FILE* f = fopen(p.c_str(), "rb"); if (!f) return "<none>"; char b[65536]; size_t n; while ((n = fread(b, 1, sizeof b, f)) > 0) s.append(b, n); fclose(f); return s; }
static void put(const std::string& p, const std::string& s) { FILE* f = fopen(p.c_str(), "wb"); fwrite(s.data(), 1, s.size(), f); fclose(f); }
static Entry login(const std::string& o, const std::string& u, const std::string& pw) { Entry e; e.id = Vault::newId(); e.kind = "login"; e.origin = o; e.a = u; e.b = pw; e.created = 1; e.used = 2; return e; }
static uint8_t L_key[32];
static std::string legacySeal(const std::string& plain, uint64_t seed)
{
    uint8_t nonce[8]; for (int i = 0; i < 8; ++i) nonce[i] = uint8_t(seed >> (8 * i)) ^ uint8_t(i * 37);
    std::string out(reinterpret_cast<const char*>(nonce), 8); out += plain;
    uint64_t s = 0xcbf29ce484222325ull;
    for (int i = 0; i < 32; ++i) s = (s ^ L_key[i]) * 0x100000001b3ull;
    for (int i = 0; i < 8; ++i) s = (s ^ nonce[i]) * 0x100000001b3ull;
    for (size_t i = 8; i < out.size(); i += 8) { const uint64_t r = legacyMix(s); for (size_t k = 0; k < 8 && i + k < out.size(); ++k) out[i + k] = char(uint8_t(out[i + k]) ^ uint8_t(r >> (8 * k))); }
    return hex(out);
}
// A saved vault with one login; returns the directory.
static std::string savedVault()
{
    std::string d = mkdir_tmp();
    Vault v(d); v.load(); v.entries.push_back(login("https://keep.example", "me", "do not lose")); if (!v.save()) fprintf(stderr, "setup save failed\n");
    return d;
}

int main()
{
    const bool root = geteuid() == 0;
    // 1. vault.v2 bigger than the reader's limit (what an unbounded writer could produce): not "absent" -> no new key, no overwrite
    {
        std::string d = savedVault();
        const std::string key = slurp(d + "vault.key");
        std::string big = slurp(d + "vault.v2"); big.insert(big.size() - 4, std::string(kMaxFile, 'x') + "\n");   // before "end"
        put(d + "vault.v2", big); unlink((d + "vault.v2.bak").c_str());
        Vault v(d); CHECK(!v.load()); CHECK(v.openFailed()); CHECK(!v.canSave());
        v.entries.push_back(login("https://new.example", "x", "y")); CHECK(!v.save());
        CHECK(slurp(d + "vault.key") == key); CHECK(slurp(d + "vault.v2") == big);
        CHECK(v.setPin("123456 pin") == false); CHECK(slurp(d + "vault.key") == key);
        rmrf(d);
    }
    // 2. vault.v2 is there but not a readable regular file (a directory: read error): fail closed, key kept
    {
        std::string d = savedVault();
        const std::string key = slurp(d + "vault.key");
        rename((d + "vault.v2").c_str(), (d + "moved").c_str()); mkdir((d + "vault.v2").c_str(), 0700);
        Vault v(d); CHECK(!v.load()); CHECK(v.openFailed()); CHECK(!v.save()); CHECK(slurp(d + "vault.key") == key);
        rmrf(d);
    }
    // 3. permission denied on vault.v2 (non-root only): never treated as a new vault
    if (!root) {
        std::string d = savedVault();
        const std::string key = slurp(d + "vault.key"), file = slurp(d + "vault.v2");
        unlink((d + "vault.v2.bak").c_str()); chmod((d + "vault.v2").c_str(), 0);
        Vault v(d); CHECK(!v.load()); CHECK(v.openFailed()); CHECK(v.exists());
        v.entries.push_back(login("https://new.example", "x", "y")); CHECK(!v.save());
        chmod((d + "vault.v2").c_str(), 0600);
        CHECK(slurp(d + "vault.key") == key); CHECK(slurp(d + "vault.v2") == file);
        Vault w(d); CHECK(w.load()); CHECK(w.entries.size() == 1 && w.entries[0].b == "do not lose");
        rmrf(d);
    } else printf("(running as root: permission cases skipped; the size and directory cases cover the same paths)\n");
    // 4. vault.v2 absent, backup unreadable: not a new vault either
    {
        std::string d = savedVault();
        Vault s(d); s.load(); s.save();                          // makes vault.v2.bak
        const std::string key = slurp(d + "vault.key"), bak = slurp(d + "vault.v2.bak");
        unlink((d + "vault.v2").c_str());
        std::string big = bak; big.insert(big.size() - 4, std::string(kMaxFile, 'x') + "\n"); put(d + "vault.v2.bak", big);
        Vault v(d); CHECK(!v.load()); CHECK(v.openFailed()); CHECK(!v.save()); CHECK(slurp(d + "vault.key") == key); CHECK(!fileExists(d + "vault.v2"));
        rmrf(d);
    }
    // 5. vault.key there but unreadable: open refused, nothing replaced
    {
        std::string d = savedVault();
        const std::string file = slurp(d + "vault.v2");
        rename((d + "vault.key").c_str(), (d + "key.saved").c_str()); mkdir((d + "vault.key").c_str(), 0700);
        Vault v(d); CHECK(!v.load()); CHECK(v.openFailed()); CHECK(!v.save()); CHECK(slurp(d + "vault.v2") == file);
        rmdir((d + "vault.key").c_str()); rename((d + "key.saved").c_str(), (d + "vault.key").c_str());
        Vault w(d); CHECK(w.load()); CHECK(w.entries.size() == 1);
        rmrf(d);
    }
    // 6. a save that would produce a file the reader refuses is not written; the previous vault stays loadable
    {
        std::string d = savedVault();
        const std::string file = slurp(d + "vault.v2");
        Vault v(d); CHECK(v.load());
        for (int i = 0; i < 1200; ++i) v.entries.push_back(login("https://big" + std::to_string(i) + ".example", std::string(4096, 'u'), std::string(4096, 'p')));
        CHECK(!v.save()); CHECK(slurp(d + "vault.v2") == file);
        Vault w(d); CHECK(w.load()); CHECK(!w.recoveredFromBackup()); CHECK(w.entries.size() == 1);
        rmrf(d);
    }
    // 7. migration from the old XOR store: happy path, then the failure paths keep the old files where they are
    for (int i = 0; i < 32; ++i) L_key[i] = uint8_t(i * 11 + 5);
    const std::string keyText = hex(std::string(reinterpret_cast<const char*>(L_key), 32)) + "\n";
    const std::string txt = "omni-passwords\t1\nlogin\thttps://old.example\t" + legacySeal("olduser", 1) + "\t" + legacySeal("old pass", 2) + "\t11\t22\n";
    {   // 7a. works
        std::string d = mkdir_tmp(); put(d + "passwords.key", keyText); put(d + "passwords.txt", txt);
        Vault v(d); CHECK(v.load()); int bad = -1; CHECK(v.migrateLegacy(&bad) == 1); CHECK(bad == 0);
        Vault w(d); CHECK(w.load()); CHECK(w.entries.size() == 1 && w.entries[0].b == "old pass");
        CHECK(slurp(d + "passwords.txt.xor-migrated") == txt && slurp(d + "passwords.key.xor-migrated") == keyText);
        rmrf(d);
    }
    {   // 7b. old key exists but can't be read: nothing imported, nothing renamed (before: all lines "undecodable", files retired)
        std::string d = mkdir_tmp(); put(d + "passwords.txt", txt); mkdir((d + "passwords.key").c_str(), 0700);
        Vault v(d); CHECK(v.load()); CHECK(v.migrateLegacy() == -1);
        CHECK(slurp(d + "passwords.txt") == txt); CHECK(!fileExists(d + "passwords.txt.xor-migrated")); CHECK(!fileExists(d + "passwords.key.xor-migrated"));
        rmdir((d + "passwords.key").c_str()); put(d + "passwords.key", keyText);
        Vault w(d); CHECK(w.load()); CHECK(w.migrateLegacy() == 1);   // retried on the next start once readable
        rmrf(d);
    }
    {   // 7c. old store exists but can't be read: reported as a failure, not as "nothing to migrate"
        std::string d = mkdir_tmp(); put(d + "passwords.key", keyText);
        std::string bigTxt = txt + std::string(kMaxFile, '#'); put(d + "passwords.txt", bigTxt);
        Vault v(d); CHECK(v.load()); CHECK(v.migrateLegacy() == -1);
        CHECK(fileExists(d + "passwords.txt") && fileExists(d + "passwords.key") && !fileExists(d + "passwords.txt.xor-migrated"));
        rmrf(d);
    }
    {   // 7d. the new vault can't be read: migration refused, old files untouched, new vault not created over it
        std::string d = savedVault(); const std::string key = slurp(d + "vault.key");
        rename((d + "vault.v2").c_str(), (d + "moved").c_str()); mkdir((d + "vault.v2").c_str(), 0700);
        put(d + "passwords.key", keyText); put(d + "passwords.txt", txt);
        Vault v(d); CHECK(!v.load()); CHECK(v.migrateLegacy() == -1);
        CHECK(slurp(d + "passwords.txt") == txt && slurp(d + "vault.key") == key);
        rmrf(d);
    }
    {   // 7e. a wrong old key (decrypt failure) keeps the undecodable lines in the retired file byte for byte
        std::string d = mkdir_tmp(); std::string wrong(32, '\x55'); put(d + "passwords.key", hex(wrong) + "\n"); put(d + "passwords.txt", txt);
        Vault v(d); CHECK(v.load()); int bad = -1; const int n = v.migrateLegacy(&bad);
        CHECK(n == 0 || n == 1);   // XOR has no integrity check: a wrong key yields garbage or nothing, never a crash
        CHECK(slurp(d + "passwords.txt.xor-migrated") == txt);
        rmrf(d);
    }
    printf("VAULT OS-002 TESTS: %d passed, %d failed\n", passes, fails);
    return fails ? 1 : 0;
}
