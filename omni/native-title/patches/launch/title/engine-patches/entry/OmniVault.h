// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_VAULT_V2: encrypted storage for saved logins and 2FA (TOTP) secrets.
//
// Replaces the OMNI_FEATURES_V2 password store, which XORed each value with a keystream made from a key
// file stored next to the data (obfuscation, not encryption).
//
// Crypto: AES-256-GCM (OpenSSL EVP) for every entry, with a fresh random 96-bit nonce on every save and
// authenticated data that binds the entry to its kind, id, origin and timestamps. A copied or edited entry
// fails its tag and is never shown or filled.
//
// Keys: one random 256-bit data key (RAND_bytes).
//  * Default ("file" mode): the data key is kept in /data/omni/vault.key (mode 0600).
//    HONEST LIMIT: anyone who can read the console's files (for example over the jailbreak's FTP server on
//    the home network) can read vault.key and decrypt the vault. This is much better than XOR (no fixed
//    keystream, tamper detection, no key reuse across values) but it is NOT protection from someone with
//    file access. Use PIN mode for that.
//  * PIN mode: the data key is wrapped with AES-256-GCM under a key derived from the user's PIN with
//    PBKDF2-HMAC-SHA256 (iterations stored in the file, default 600,000) and a random 128-bit salt.
//    vault.key is removed. Nothing on the console can decrypt the vault without the PIN.
//
// Files (all in the data dir, written atomically: temp file + fsync + rename + directory fsync):
//   vault.v2      the vault          vault.v2.bak   the previous good version (used if vault.v2 is damaged)
//   vault.key     file mode only
// The vault is never overwritten when it can't be opened (missing key, locked, unreadable): saves are refused.
// Entries that fail authentication are kept byte-for-byte and written back unchanged, never dropped.
//
// Migration from OMNI_FEATURES_V2: passwords.txt + passwords.key are read once, re-encrypted, and renamed
// to *.xor-migrated (never deleted). Lines that can't be decoded stay in the renamed file.
#pragma once
#include <string>
#include <vector>
#include <cstring>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>

#if defined(__has_include) && !defined(OMNI_VAULT_NO_OPENSSL_HEADERS)
#  if __has_include(<openssl/evp.h>) && __has_include(<openssl/rand.h>)
#    include <openssl/evp.h>
#    include <openssl/rand.h>
#    include <openssl/crypto.h>
#    define OMNI_VAULT_HAVE_OPENSSL_HEADERS 1
#  endif
#endif
#ifndef OMNI_VAULT_HAVE_OPENSSL_HEADERS
// The shell's compile flags may not carry OpenSSL's include path; the title links libcrypto.a (OpenSSL 3.5.9)
// either way. These are the exact OpenSSL 3 declarations of the functions used below.
extern "C" {
typedef struct evp_cipher_ctx_st EVP_CIPHER_CTX;
typedef struct evp_cipher_st EVP_CIPHER;
typedef struct evp_md_st EVP_MD;
typedef struct engine_st ENGINE;
EVP_CIPHER_CTX* EVP_CIPHER_CTX_new(void);
void EVP_CIPHER_CTX_free(EVP_CIPHER_CTX* ctx);
const EVP_CIPHER* EVP_aes_256_gcm(void);
int EVP_EncryptInit_ex(EVP_CIPHER_CTX* ctx, const EVP_CIPHER* type, ENGINE* impl, const unsigned char* key, const unsigned char* iv);
int EVP_DecryptInit_ex(EVP_CIPHER_CTX* ctx, const EVP_CIPHER* type, ENGINE* impl, const unsigned char* key, const unsigned char* iv);
int EVP_EncryptUpdate(EVP_CIPHER_CTX* ctx, unsigned char* out, int* outl, const unsigned char* in, int inl);
int EVP_DecryptUpdate(EVP_CIPHER_CTX* ctx, unsigned char* out, int* outl, const unsigned char* in, int inl);
int EVP_EncryptFinal_ex(EVP_CIPHER_CTX* ctx, unsigned char* out, int* outl);
int EVP_DecryptFinal_ex(EVP_CIPHER_CTX* ctx, unsigned char* outm, int* outl);
int EVP_CIPHER_CTX_ctrl(EVP_CIPHER_CTX* ctx, int type, int arg, void* ptr);
int PKCS5_PBKDF2_HMAC(const char* pass, int passlen, const unsigned char* salt, int saltlen, int iter, const EVP_MD* digest, int keylen, unsigned char* out);
const EVP_MD* EVP_sha256(void);
int RAND_bytes(unsigned char* buf, int num);
void OPENSSL_cleanse(void* ptr, size_t len);
int CRYPTO_memcmp(const void* a, const void* b, size_t len);
}
#  define EVP_CTRL_GCM_SET_IVLEN 0x9
#  define EVP_CTRL_GCM_GET_TAG 0x10
#  define EVP_CTRL_GCM_SET_TAG 0x11
#endif

namespace OmniVault {

static const int kDefaultIterations = 600000;
static const size_t kMaxEntries = 2000, kMaxField = 4096, kMaxFile = 8u << 20;

// ---- small helpers --------------------------------------------------------------------------------
static inline std::string hex(const std::string& b)
{
    static const char* h = "0123456789abcdef";
    std::string o; o.reserve(b.size() * 2);
    for (unsigned char c : b) { o += h[c >> 4]; o += h[c & 15]; }
    return o;
}
static inline bool unhex(const std::string& h, std::string& out)
{
    out.clear();
    if (h.size() % 2) return false;
    auto v = [](char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; };
    out.reserve(h.size() / 2);
    for (size_t i = 0; i < h.size(); i += 2) { const int a = v(h[i]), b = v(h[i + 1]); if (a < 0 || b < 0) return false; out += char(a * 16 + b); }
    return true;
}
static inline void wipe(std::string& s) { if (!s.empty()) OPENSSL_cleanse(&s[0], s.size()); s.clear(); }
static inline void wipe(void* p, size_t n) { OPENSSL_cleanse(p, n); }
static inline bool randomBytes(void* out, size_t n) { return RAND_bytes(static_cast<unsigned char*>(out), int(n)) == 1; }
static inline std::vector<std::string> splitTabs(const std::string& s)
{
    std::vector<std::string> part; size_t from = 0;
    for (;;) { const size_t t = s.find('\t', from); part.push_back(s.substr(from, t == std::string::npos ? std::string::npos : t - from)); if (t == std::string::npos) break; from = t + 1; }
    return part;
}
static inline std::string oneLine(std::string s, size_t max)
{
    for (auto& c : s) if (c == '\t' || c == '\n' || c == '\r') c = ' ';
    if (s.size() > max) s.resize(max);
    return s;
}

// ---- AES-256-GCM ----------------------------------------------------------------------------------
static inline bool gcmSeal(const uint8_t key[32], const std::string& aad, const std::string& plain, std::string& nonce, std::string& ct, std::string& tag)
{
    nonce.assign(12, '\0'); ct.assign(plain.size(), '\0'); tag.assign(16, '\0');
    if (!randomBytes(&nonce[0], 12)) return false;
    EVP_CIPHER_CTX* c = EVP_CIPHER_CTX_new();
    if (!c) return false;
    int n = 0, ok = 1;
    ok &= EVP_EncryptInit_ex(c, EVP_aes_256_gcm(), nullptr, nullptr, nullptr);
    ok &= EVP_CIPHER_CTX_ctrl(c, EVP_CTRL_GCM_SET_IVLEN, 12, nullptr);
    ok &= EVP_EncryptInit_ex(c, nullptr, nullptr, key, reinterpret_cast<const unsigned char*>(nonce.data()));
    if (ok && !aad.empty()) ok &= EVP_EncryptUpdate(c, nullptr, &n, reinterpret_cast<const unsigned char*>(aad.data()), int(aad.size()));
    if (ok && !plain.empty()) ok &= EVP_EncryptUpdate(c, reinterpret_cast<unsigned char*>(&ct[0]), &n, reinterpret_cast<const unsigned char*>(plain.data()), int(plain.size()));
    unsigned char fin[16]; int fl = 0;
    if (ok) ok &= EVP_EncryptFinal_ex(c, fin, &fl);
    if (ok) ok &= EVP_CIPHER_CTX_ctrl(c, EVP_CTRL_GCM_GET_TAG, 16, &tag[0]);
    EVP_CIPHER_CTX_free(c);
    return ok == 1;
}
static inline bool gcmOpen(const uint8_t key[32], const std::string& aad, const std::string& nonce, const std::string& ct, const std::string& tag, std::string& plain)
{
    plain.clear();
    if (nonce.size() != 12 || tag.size() != 16) return false;
    std::string out(ct.size(), '\0');
    EVP_CIPHER_CTX* c = EVP_CIPHER_CTX_new();
    if (!c) return false;
    int n = 0, ok = 1;
    ok &= EVP_DecryptInit_ex(c, EVP_aes_256_gcm(), nullptr, nullptr, nullptr);
    ok &= EVP_CIPHER_CTX_ctrl(c, EVP_CTRL_GCM_SET_IVLEN, 12, nullptr);
    ok &= EVP_DecryptInit_ex(c, nullptr, nullptr, key, reinterpret_cast<const unsigned char*>(nonce.data()));
    if (ok && !aad.empty()) ok &= EVP_DecryptUpdate(c, nullptr, &n, reinterpret_cast<const unsigned char*>(aad.data()), int(aad.size()));
    if (ok && !ct.empty()) ok &= EVP_DecryptUpdate(c, reinterpret_cast<unsigned char*>(&out[0]), &n, reinterpret_cast<const unsigned char*>(ct.data()), int(ct.size()));
    std::string t = tag;
    if (ok) ok &= EVP_CIPHER_CTX_ctrl(c, EVP_CTRL_GCM_SET_TAG, 16, &t[0]);
    unsigned char fin[16]; int fl = 0;
    if (ok) ok &= (EVP_DecryptFinal_ex(c, fin, &fl) > 0);   // fails when the tag doesn't match
    EVP_CIPHER_CTX_free(c);
    if (ok != 1) { wipe(out); return false; }
    plain.swap(out);
    return true;
}
static inline bool deriveKey(const std::string& pin, const std::string& salt, int iterations, uint8_t out[32])
{
    return PKCS5_PBKDF2_HMAC(pin.data(), int(pin.size()), reinterpret_cast<const unsigned char*>(salt.data()), int(salt.size()), iterations, EVP_sha256(), 32, out) == 1;
}

// ---- files ------------------------------------------------------------------------------------------
static int (*testCrashPoint)(const char* where) = nullptr;   // host tests only: return nonzero to "crash" there
// OS-002: a read tells "the file isn't there" (Absent: only ENOENT) apart from "it is there but can't be read"
// (Error: permission, I/O error, not a regular file, too big). Only Absent may ever lead to a new, empty vault.
enum class Read { Ok, Absent, Error };
static inline Read readFileEx(const std::string& path, std::string& out)
{
    out.clear();
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return errno == ENOENT ? Read::Absent : Read::Error;
    struct stat st;
    if (fstat(fileno(f), &st) != 0 || !S_ISREG(st.st_mode)) { fclose(f); return Read::Error; }
    char buf[16384]; size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0) { out.append(buf, n); if (out.size() > kMaxFile) { fclose(f); wipe(out); return Read::Error; } }
    const bool failed = ferror(f) != 0;
    fclose(f);
    if (failed) { wipe(out); return Read::Error; }
    return Read::Ok;
}
static inline bool readFile(const std::string& path, std::string& out) { return readFileEx(path, out) == Read::Ok; }
static inline bool fileExists(const std::string& path) { struct stat st; return stat(path.c_str(), &st) == 0; }
static inline void syncDir(const std::string& dir)
{
    const int fd = ::open(dir.c_str(), O_RDONLY);
    if (fd >= 0) { (void)fsync(fd); close(fd); }
}
// temp file + fsync + rename + directory fsync. The old file stays intact until the rename.
static inline bool writeAtomic(const std::string& dir, const std::string& path, const std::string& data, mode_t mode)
{
    const std::string tmp = path + ".tmp";
    const int fd = ::open(tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC, mode);
    if (fd < 0) return false;
    size_t done = 0;
    if (testCrashPoint && testCrashPoint("mid-write")) { (void)!write(fd, data.data(), data.size() / 2); close(fd); return false; }
    while (done < data.size()) { const ssize_t w = write(fd, data.data() + done, data.size() - done); if (w <= 0) { close(fd); unlink(tmp.c_str()); return false; } done += size_t(w); }
    if (fsync(fd) != 0) { close(fd); unlink(tmp.c_str()); return false; }
    close(fd);
    (void)chmod(tmp.c_str(), mode);
    if (testCrashPoint && testCrashPoint("before-rename")) return false;
    if (rename(tmp.c_str(), path.c_str()) != 0) { unlink(tmp.c_str()); return false; }
    syncDir(dir);
    return true;
}

// ---- the legacy OMNI_FEATURES_V2 format (read-only, for migration) ------------------------------
static inline uint64_t legacyMix(uint64_t& s)
{
    uint64_t z = (s += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}
static inline bool legacyUnseal(const uint8_t key[32], const std::string& hexValue, std::string& plain)
{
    std::string raw;
    if (!unhex(hexValue, raw) || raw.size() < 8) return false;
    uint64_t s = 0xcbf29ce484222325ull;
    for (int i = 0; i < 32; ++i) s = (s ^ key[i]) * 0x100000001b3ull;
    for (int i = 0; i < 8; ++i) s = (s ^ uint8_t(raw[i])) * 0x100000001b3ull;
    for (size_t i = 8; i < raw.size(); i += 8) {
        const uint64_t r = legacyMix(s);
        for (size_t k = 0; k < 8 && i + k < raw.size(); ++k) raw[i + k] = char(uint8_t(raw[i + k]) ^ uint8_t(r >> (8 * k)));
    }
    plain = raw.substr(8);
    wipe(raw);
    return true;
}

// ---- the vault ---------------------------------------------------------------------------------------
struct Entry {
    std::string id;       // 16 hex chars, random
    std::string kind;     // "login" or "totp"
    std::string origin;   // login: scheme://host[:port]; totp: issuer/account label shown in lists
    long long created = 0, used = 0;
    std::string a, b, c;  // login: user, password, -;  totp: account label, base32 secret, "SHA1,6,30"
};

class Vault {
public:
    explicit Vault(std::string dir) : dir_(std::move(dir)) { if (!dir_.empty() && dir_.back() != '/') dir_ += '/'; }
    ~Vault() { lock(); }

    // State, for the UI and for vault.capabilities.
    bool exists() const { return exists_; }
    bool pinMode() const { return pinMode_; }
    bool unlocked() const { return haveKey_; }
    bool openFailed() const { return openFailed_; }       // file present but can't be opened: never overwritten
    bool recoveredFromBackup() const { return fromBackup_; }
    size_t unreadable() const { return badRaw_.size(); }  // entries whose authentication failed (kept as they are)
    const std::string& error() const { return error_; }
    int iterations() const { return iterations_; }
    std::vector<Entry> entries;                            // decrypted entries (empty while locked)

    std::string path(const char* name) const { return dir_ + name; }

    // Reads vault.v2 (or .bak). In file mode it also reads vault.key and decrypts. In PIN mode it stays locked.
    bool load()
    {
        lock(); clearState();
        std::string text;
        for (const char* name : { "vault.v2", "vault.v2.bak" }) {
            const Read r = readFileEx(path(name), text);
            if (r == Read::Absent) continue;
            exists_ = true;
            if (r == Read::Error) {                          // OS-002: there but unreadable: never treated as new, never written
                wipe(text); clearParsed(); openFailed_ = true;
                error_ = std::string("The vault file ") + name + " can't be read";
                return false;
            }
            if (parse(text)) { fromBackup_ = std::strcmp(name, "vault.v2.bak") == 0; loadedText_ = text; break; }
            clearParsed();
        }
        wipe(text);
        if (!exists_) return true;                           // a new, empty vault (both files confirmed absent)
        if (!parsedOk_) { openFailed_ = true; error_ = "The vault file is damaged and its backup can't be read"; return false; }
        if (pinMode_) return true;                           // locked until unlock()
        std::string keyHex, key;
        const Read kr = readFileEx(path("vault.key"), keyHex);
        if (kr != Read::Ok) { wipe(keyHex); openFailed_ = true; error_ = kr == Read::Absent ? "The vault key file is missing" : "The vault key file can't be read"; return false; }
        while (!keyHex.empty() && (keyHex.back() == '\n' || keyHex.back() == '\r')) keyHex.pop_back();
        if (!unhex(keyHex, key) || key.size() != 32) { wipe(keyHex); openFailed_ = true; error_ = "The vault key file is damaged"; return false; }
        memcpy(key_, key.data(), 32); wipe(key); wipe(keyHex);
        if (!checkKey()) { wipe(key_, 32); openFailed_ = true; error_ = "The vault key doesn't match this vault"; return false; }
        haveKey_ = true;
        decryptAll();
        return true;
    }

    // PIN mode: derive the key-encryption key and unwrap the data key. Wrong PIN -> false (GCM tag fails).
    bool unlock(const std::string& pin)
    {
        if (!pinMode_ || haveKey_) return haveKey_;
        if (!loadedText_.empty()) { std::string t = loadedText_; const bool ok = parse(t); wipe(t); if (!ok) { error_ = "The vault file is damaged"; return false; } }
        uint8_t kek[32];
        if (!deriveKey(pin, salt_, iterations_, kek)) { error_ = "Key derivation failed"; return false; }
        std::string dk;
        const bool ok = gcmOpen(kek, "omni-vault-v2 key", wrapNonce_, wrapCt_, wrapTag_, dk) && dk.size() == 32;
        wipe(kek, 32);
        if (!ok) { wipe(dk); error_ = "Wrong PIN"; return false; }
        memcpy(key_, dk.data(), 32); wipe(dk);
        if (!checkKey()) { wipe(key_, 32); error_ = "Wrong PIN"; return false; }
        haveKey_ = true; error_.clear();
        decryptAll();
        return true;
    }
    void lock()
    {
        for (auto& e : entries) { wipe(e.a); wipe(e.b); wipe(e.c); }
        entries.clear();
        wipe(key_, 32);
        haveKey_ = false;
    }
    bool canSave() const { return !openFailed_ && (haveKey_ || (!exists_ && !pinMode_)); }

    // Re-encrypts every entry with fresh nonces and writes atomically (previous version kept as .bak).
    bool save()
    {
        if (!canSave()) { if (error_.empty()) error_ = pinMode_ ? "The vault is locked" : "The vault can't be opened"; return false; }
        if (!haveKey_) {   // first save of a new vault: create the data key and its file first
            if (!randomBytes(key_, 32)) { error_ = "No random numbers available"; return false; }
            std::string k(reinterpret_cast<const char*>(key_), 32);
            const bool ok = writeAtomic(dir_, path("vault.key"), hex(k) + "\n", 0600);
            wipe(k);
            if (!ok) { wipe(key_, 32); error_ = "Couldn't write the vault key"; return false; }
            haveKey_ = true; exists_ = true;
        }
        std::string text;
        if (!build(text)) { error_ = "Encryption failed or the vault is too large"; return false; }
        if (!loadedText_.empty() && !writeAtomic(dir_, path("vault.v2.bak"), loadedText_, 0600)) { wipe(text); error_ = "Couldn't write the backup"; return false; }
        if (!writeAtomic(dir_, path("vault.v2"), text, 0600)) { wipe(text); error_ = "Couldn't write the vault"; return false; }
        wipe(loadedText_); loadedText_.swap(text);
        exists_ = true; fromBackup_ = false; error_.clear();
        return true;
    }

    // Turns PIN mode on (or changes the PIN). A NEW data key is made and everything is re-encrypted under it,
    // the backup is rewritten under it too, and vault.key is removed, so the old key file opens nothing.
    bool setPin(const std::string& pin, int iterations = kDefaultIterations)
    {
        if (pin.size() < 6) { error_ = "Use at least 6 characters"; return false; }
        if (exists_ && !haveKey_) { error_ = "Unlock the vault first"; return false; }
        if (openFailed_) { error_ = "The vault can't be opened"; return false; }
        uint8_t newKey[32], kek[32];
        std::string salt(16, '\0');
        if (!randomBytes(newKey, 32) || !randomBytes(&salt[0], 16)) { error_ = "No random numbers available"; return false; }
        if (!deriveKey(pin, salt, iterations, kek)) { wipe(newKey, 32); error_ = "Key derivation failed"; return false; }
        std::string dk(reinterpret_cast<const char*>(newKey), 32), n, ct, tag;
        const bool ok = gcmSeal(kek, "omni-vault-v2 key", dk, n, ct, tag);
        wipe(dk); wipe(kek, 32);
        if (!ok) { wipe(newKey, 32); error_ = "Encryption failed"; return false; }
        const bool wasPin = pinMode_; const std::string oldSalt = salt_; const int oldIter = iterations_;
        const std::string oN = wrapNonce_, oC = wrapCt_, oT = wrapTag_;
        uint8_t oldKey[32]; memcpy(oldKey, key_, 32); const bool hadKey = haveKey_;
        pinMode_ = true; salt_ = salt; iterations_ = iterations; wrapNonce_ = n; wrapCt_ = ct; wrapTag_ = tag;
        memcpy(key_, newKey, 32); haveKey_ = true; wipe(newKey, 32);
        std::string text;
        bool good = build(text) && writeAtomic(dir_, path("vault.v2.bak"), text, 0600) && writeAtomic(dir_, path("vault.v2"), text, 0600);
        if (!good) {   // put everything back as it was; the files on disk are unchanged or a consistent new version
            pinMode_ = wasPin; salt_ = oldSalt; iterations_ = oldIter; wrapNonce_ = oN; wrapCt_ = oC; wrapTag_ = oT;
            memcpy(key_, oldKey, 32); haveKey_ = hadKey; wipe(oldKey, 32); wipe(text);
            error_ = "Couldn't write the vault"; return false;
        }
        wipe(oldKey, 32);
        wipe(loadedText_); loadedText_.swap(text);
        exists_ = true;
        unlink(path("vault.key").c_str()); syncDir(dir_);   // the old key can no longer open anything current
        error_.clear();
        return true;
    }
    // Back to file mode (needs the vault unlocked). Writes vault.key with a new data key.
    bool removePin()
    {
        if (!pinMode_) return true;
        if (!haveKey_) { error_ = "Unlock the vault first"; return false; }
        uint8_t newKey[32];
        if (!randomBytes(newKey, 32)) { error_ = "No random numbers available"; return false; }
        std::string k(reinterpret_cast<const char*>(newKey), 32);
        if (!writeAtomic(dir_, path("vault.key.new"), hex(k) + "\n", 0600)) { wipe(k); wipe(newKey, 32); error_ = "Couldn't write the vault key"; return false; }
        wipe(k);
        uint8_t oldKey[32]; memcpy(oldKey, key_, 32);
        pinMode_ = false; memcpy(key_, newKey, 32); wipe(newKey, 32);
        std::string text;
        if (!(build(text) && writeAtomic(dir_, path("vault.v2.bak"), text, 0600))) {
            pinMode_ = true; memcpy(key_, oldKey, 32); wipe(oldKey, 32); wipe(text); unlink(path("vault.key.new").c_str());
            error_ = "Couldn't write the vault"; return false;
        }
        // the key must exist under its real name before the vault that needs it
        if (rename(path("vault.key.new").c_str(), path("vault.key").c_str()) != 0 || !writeAtomic(dir_, path("vault.v2"), text, 0600)) {
            pinMode_ = true; memcpy(key_, oldKey, 32); wipe(oldKey, 32); wipe(text);
            error_ = "Couldn't write the vault"; return false;
        }
        syncDir(dir_);
        wipe(oldKey, 32);
        wipe(loadedText_); loadedText_.swap(text);
        error_.clear();
        return true;
    }

    // One-time import of the OMNI_FEATURES_V2 store. Returns the number imported, or -1 on failure.
    // passwords.txt/passwords.key are renamed to *.xor-migrated (a timestamp is added if that name exists).
    int migrateLegacy(int* undecodable = nullptr)
    {
        if (undecodable) *undecodable = 0;
        const std::string txt = path("passwords.txt"), keyFile = path("passwords.key");
        if (!fileExists(txt)) return 0;
        if (!canSave()) { error_ = openFailed_ ? error_ : "Unlock the vault first"; return -1; }
        uint8_t key[32]; bool haveLegacyKey = false;
        std::string s, raw;
        // OS-002: if the old key or the old store exists but can't be read, nothing is imported and nothing is renamed,
        // so the next start tries again. (A missing key still imports nothing and keeps the lines, as before.)
        const Read kr = readFileEx(keyFile, s);
        if (kr == Read::Error) { wipe(s); error_ = "The old passwords key can't be read"; return -1; }
        if (kr == Read::Ok) {
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            if (unhex(s, raw) && raw.size() == 32) { memcpy(key, raw.data(), 32); haveLegacyKey = true; }
            wipe(raw); wipe(s);
        }
        std::string text;
        const Read tr = readFileEx(txt, text);
        if (tr != Read::Ok) { wipe(text); wipe(key, 32); if (tr == Read::Absent) return 0; error_ = "The old passwords file can't be read"; return -1; }
        int added = 0, bad = 0;
        size_t from = 0;
        while (from < text.size()) {
            size_t nl = text.find('\n', from); if (nl == std::string::npos) nl = text.size();
            std::string line = text.substr(from, nl - from); from = nl + 1;
            while (!line.empty() && line.back() == '\r') line.pop_back();
            auto part = splitTabs(line);
            if (part.size() >= 6 && part[0] == "login") {
                Entry e; e.kind = "login"; e.origin = oneLine(part[1], 300);
                e.created = atoll(part[4].c_str()); e.used = atoll(part[5].c_str());
                if (haveLegacyKey && legacyUnseal(key, part[2], e.a) && legacyUnseal(key, part[3], e.b)) {
                    bool dup = false;
                    for (auto& x : entries) if (x.kind == "login" && x.origin == e.origin && x.a == e.a && x.b == e.b) dup = true;
                    if (!dup && entries.size() < kMaxEntries) { e.id = newId(); entries.push_back(std::move(e)); ++added; }
                    else { wipe(e.a); wipe(e.b); }
                } else ++bad;
            }
            wipe(line);
        }
        wipe(text); wipe(key, 32);
        if (undecodable) *undecodable = bad;
        if (!save()) return -1;   // the old files stay where they were if the new vault couldn't be written
        auto retire = [&](const std::string& p) {
            if (!fileExists(p)) return;
            std::string to = p + ".xor-migrated";
            if (fileExists(to)) to += "-" + std::to_string((long long)time(nullptr));
            (void)rename(p.c_str(), to.c_str());
        };
        retire(txt); retire(keyFile); syncDir(dir_);
        return added;
    }
    bool legacyLeftovers() const { return fileExists(path("passwords.txt.xor-migrated")) || fileExists(path("passwords.key.xor-migrated")); }

    static std::string newId()
    {
        std::string b(8, '\0');
        if (!randomBytes(&b[0], 8)) { for (auto& c : b) c = char(rand()); }
        return hex(b);
    }

private:
    struct Raw { std::string line, id, kind, origin, nonce, ct, tag; long long created = 0, used = 0; };
    std::string dir_, error_, salt_, wrapNonce_, wrapCt_, wrapTag_, checkNonce_, checkCt_, checkTag_, loadedText_;
    uint8_t key_[32] {};
    bool exists_ = false, pinMode_ = false, haveKey_ = false, openFailed_ = false, fromBackup_ = false, parsedOk_ = false;
    int iterations_ = kDefaultIterations;
    std::vector<Raw> raw_;      // parsed, still encrypted
    std::vector<Raw> parseBad_; // malformed entry lines from the file
    std::vector<Raw> badRaw_;   // malformed + failed authentication: written back byte-for-byte

    void clearParsed()
    {
        parsedOk_ = false; pinMode_ = false; salt_.clear(); wrapNonce_.clear(); wrapCt_.clear(); wrapTag_.clear();
        checkNonce_.clear(); checkCt_.clear(); checkTag_.clear(); raw_.clear(); parseBad_.clear(); badRaw_.clear(); iterations_ = kDefaultIterations;
    }
    void clearState() { clearParsed(); exists_ = openFailed_ = fromBackup_ = false; error_.clear(); wipe(loadedText_); }

    static std::string aadFor(const std::string& kind, const std::string& id, const std::string& origin, long long created, long long used)
    {
        return "omni-vault-v2\n" + kind + "\n" + id + "\n" + origin + "\n" + std::to_string(created) + "\n" + std::to_string(used);
    }
    bool parse(const std::string& text)
    {
        clearParsed();
        size_t from = 0; int line = 0; bool header = false, haveCheck = false, haveKdf = false;
        while (from < text.size()) {
            size_t nl = text.find('\n', from); if (nl == std::string::npos) nl = text.size();
            std::string l = text.substr(from, nl - from); from = nl + 1; ++line;
            if (l.empty()) continue;
            auto p = splitTabs(l);
            std::string a, b, c;
            if (line == 1) { if (p.size() != 2 || p[0] != "omni-vault" || p[1] != "2") return false; header = true; continue; }
            if (p[0] == "kdf") {
                if (p.size() == 2 && p[1] == "none") { pinMode_ = false; haveKdf = true; }
                else if (p.size() == 4 && p[1] == "pbkdf2-sha256" && unhex(p[3], salt_) && salt_.size() == 16) {
                    iterations_ = atoi(p[2].c_str()); if (iterations_ < 10000 || iterations_ > 50000000) return false;
                    pinMode_ = true; haveKdf = true;
                } else return false;
            } else if (p[0] == "wrap" && p.size() == 4) {
                if (!unhex(p[1], wrapNonce_) || !unhex(p[2], wrapCt_) || !unhex(p[3], wrapTag_)) return false;
            } else if (p[0] == "check" && p.size() == 4) {
                if (!unhex(p[1], checkNonce_) || !unhex(p[2], checkCt_) || !unhex(p[3], checkTag_)) return false;
                haveCheck = true;
            } else if (p[0] == "entry" && p.size() == 9) {
                Raw r; r.line = l; r.id = p[1]; r.kind = p[2]; r.origin = p[3]; r.created = atoll(p[4].c_str()); r.used = atoll(p[5].c_str());
                if (r.id.size() != 16 || (r.kind != "login" && r.kind != "totp") || !unhex(p[6], r.nonce) || !unhex(p[7], r.ct) || !unhex(p[8], r.tag) || r.ct.size() > 3 * kMaxField) {
                    parseBad_.push_back(r); badRaw_.push_back(r);
                } else if (raw_.size() < kMaxEntries) raw_.push_back(std::move(r));
            } else if (p[0] == "end") {
                // trailer present: the file was written completely
                parsedOk_ = header && haveKdf && haveCheck && (!pinMode_ || !wrapCt_.empty());
                return parsedOk_;
            }
            // unknown lines from a newer version are ignored
        }
        return false;   // no trailer: incomplete file
    }
    bool checkKey()
    {
        std::string plain;
        const bool ok = gcmOpen(key_, "omni-vault-v2 check", checkNonce_, checkCt_, checkTag_, plain) && plain == "omni-vault-check";
        wipe(plain);
        return ok;
    }
    void decryptAll()
    {
        for (auto& e : entries) { wipe(e.a); wipe(e.b); wipe(e.c); }
        entries.clear();
        std::vector<Raw> stillBad = parseBad_;
        for (auto& r : raw_) {
            std::string plain;
            if (!gcmOpen(key_, aadFor(r.kind, r.id, r.origin, r.created, r.used), r.nonce, r.ct, r.tag, plain)) { stillBad.push_back(r); continue; }
            Entry e; e.id = r.id; e.kind = r.kind; e.origin = r.origin; e.created = r.created; e.used = r.used;
            const size_t z1 = plain.find('\0'), z2 = z1 == std::string::npos ? std::string::npos : plain.find('\0', z1 + 1);
            if (z1 == std::string::npos) { wipe(plain); stillBad.push_back(r); continue; }
            e.a = plain.substr(0, z1);
            e.b = plain.substr(z1 + 1, z2 == std::string::npos ? std::string::npos : z2 - z1 - 1);
            if (z2 != std::string::npos) e.c = plain.substr(z2 + 1);
            wipe(plain);
            entries.push_back(std::move(e));
        }
        badRaw_.swap(stillBad);
    }
    bool build(std::string& text)
    {
        text = "omni-vault\t2\n";
        if (pinMode_) {
            text += "kdf\tpbkdf2-sha256\t" + std::to_string(iterations_) + "\t" + hex(salt_) + "\n";
            text += "wrap\t" + hex(wrapNonce_) + "\t" + hex(wrapCt_) + "\t" + hex(wrapTag_) + "\n";
        } else text += "kdf\tnone\n";
        std::string n, ct, tag;
        if (!gcmSeal(key_, "omni-vault-v2 check", "omni-vault-check", n, ct, tag)) return false;
        text += "check\t" + hex(n) + "\t" + hex(ct) + "\t" + hex(tag) + "\n";
        size_t count = 0;
        for (auto& e : entries) {
            if (count++ >= kMaxEntries) break;
            if (e.id.size() != 16) return false;
            const std::string origin = oneLine(e.origin, 300);
            std::string plain = e.a.substr(0, kMaxField) + std::string(1, '\0') + e.b.substr(0, kMaxField);
            if (e.kind == "totp") plain += std::string(1, '\0') + e.c.substr(0, 64);
            const bool ok = gcmSeal(key_, aadFor(e.kind, e.id, origin, e.created, e.used), plain, n, ct, tag);
            wipe(plain);
            if (!ok) { wipe(text); return false; }
            text += "entry\t" + e.id + "\t" + e.kind + "\t" + origin + "\t" + std::to_string(e.created) + "\t" + std::to_string(e.used) + "\t" + hex(n) + "\t" + hex(ct) + "\t" + hex(tag) + "\n";
        }
        for (auto& r : badRaw_) text += r.line + "\n";
        text += "end\n";
        if (text.size() > kMaxFile) { wipe(text); return false; }   // OS-002: the reader refuses files this big: never write one
        return true;
    }
};

} // namespace OmniVault
