// OMNI_POINTER_STYLE_V1: pointer style, size, colour, outline and opacity (Browser settings), plus the
// user's own pointer pictures in /data/omni/pointers/. Included from OmniFeatures.h (inside OmniBrowser.cpp's
// anonymous namespace) after OmniBrowserSettings.h. OmniPointerArt.h, OmniPointerRaster.h, <zlib.h> and
// <png.h> are included at the top of OmniBrowser.cpp. The sprite is built once per setting change
// (omniPointerSprite() compares omniPtrSignature() each frame) and drawn with the chosen opacity.
#pragma once
#include "OmniPointerArrow.h"

static const char* const omniPtrColourNames[] = { "White", "Black", "Grey", "Red", "Orange", "Yellow", "Lime", "Green", "Cyan", "Blue", "Purple", "Pink" };
static const uint8_t omniPtrColours[][3] = { {255,255,255}, {20,22,28}, {150,156,166}, {235,64,52}, {255,149,0}, {255,214,10},
    {170,240,80}, {52,199,89}, {50,215,230}, {10,132,255}, {175,82,222}, {255,55,140} };
constexpr int omniPtrColourCount = int(sizeof(omniPtrColourNames) / sizeof(omniPtrColourNames[0]));
static const int omniPtrSizes[] = { 50, 75, 100, 125, 150, 175, 200, 250, 300 };
constexpr int omniPtrSizeCount = int(sizeof(omniPtrSizes) / sizeof(omniPtrSizes[0])), omniPtrSizeDefault = 2;
static const int omniPtrOpacities[] = { 100, 90, 80, 70, 60, 50, 40 };
constexpr int omniPtrOpacityCount = int(sizeof(omniPtrOpacities) / sizeof(omniPtrOpacities[0]));
constexpr float omniPtrCursorBase = 28, omniPtrCrosshairBase = 40, omniPtrPictureBase = 40; // layout px at 100% (Omni's arrow is 26 tall)
constexpr int omniPtrPictureMaxSide = 512, omniPtrPictureMaxFiles = 32;
constexpr long omniPtrPictureMaxBytes = 2 * 1024 * 1024;

// The user's pictures: /data/omni/pointers/<name>.png, hotspot at the centre or given as <name>@X,Y.png (pixels).
struct OmniPtrPicture { std::string file; int hotX = -1, hotY = -1; };
static std::vector<OmniPtrPicture> omniPtrPictures;
static bool omniPtrPicturesScanned = false;
static void omniPtrScanPictures()
{
    omniPtrPicturesScanned = true;
    omniPtrPictures.clear();
    const std::string dir = omniData("pointers");
    DIR* d = opendir(dir.c_str());
    if (!d) return;
    while (dirent* e = readdir(d)) {
        std::string n = e->d_name;
        if (n.size() < 5 || n.size() > 96 || n[0] == '.') continue;
        std::string lower = n; for (char& c : lower) c = char(tolower(static_cast<unsigned char>(c)));
        if (lower.compare(lower.size() - 4, 4, ".png")) continue;
        if (n.find('/') != std::string::npos || n.find('\t') != std::string::npos || n.find('\n') != std::string::npos) continue;
        struct stat st {};
        if (stat((dir + "/" + n).c_str(), &st) || !S_ISREG(st.st_mode) || st.st_size <= 0 || st.st_size > omniPtrPictureMaxBytes) continue;
        OmniPtrPicture p; p.file = n;
        const size_t at = n.rfind('@');
        int x = -1, y = -1;
        if (at != std::string::npos && sscanf(n.c_str() + at + 1, "%d,%d", &x, &y) == 2 && x >= 0 && y >= 0 && x <= omniPtrPictureMaxSide && y <= omniPtrPictureMaxSide) { p.hotX = x; p.hotY = y; }
        omniPtrPictures.push_back(std::move(p));
        if (int(omniPtrPictures.size()) >= 4 * omniPtrPictureMaxFiles) break;
    }
    closedir(d);
    std::sort(omniPtrPictures.begin(), omniPtrPictures.end(), [](const OmniPtrPicture& a, const OmniPtrPicture& b) { return a.file < b.file; });
    if (int(omniPtrPictures.size()) > omniPtrPictureMaxFiles) omniPtrPictures.resize(omniPtrPictureMaxFiles);
}

// Styles: 0 Omni's arrow, 1..omniPointerArtCount the built-in art, then the user's pictures. Saved by key
// ("omni", "art:<name>", "file:<file name>") so adding or removing pictures never changes the choice.
static int omniPtrStyleCount() { return 1 + omniPointerArtCount + int(omniPtrPictures.size()); }
static std::string omniPtrStyleKey(int i)
{
    if (i <= 0) return "omni";
    if (i <= omniPointerArtCount) return std::string("art:") + omniPointerArts[i - 1].name;
    const int j = i - 1 - omniPointerArtCount;
    return j < int(omniPtrPictures.size()) ? "file:" + omniPtrPictures[j].file : std::string("omni");
}
static int omniPtrStyleIndex()
{
    omniFxLoad();
    const std::string& k = omniFxSet.pstyle;
    if (k.rfind("art:", 0) == 0)
        for (int i = 0; i < omniPointerArtCount; ++i) if (k.compare(4, std::string::npos, omniPointerArts[i].name) == 0) return 1 + i;
    if (k.rfind("file:", 0) == 0) {
        if (!omniPtrPicturesScanned) omniPtrScanPictures();
        for (int j = 0; j < int(omniPtrPictures.size()); ++j) if (k.compare(5, std::string::npos, omniPtrPictures[j].file) == 0) return 1 + omniPointerArtCount + j;
    }
    return 0;
}
static std::string omniPtrStyleName(int i)
{
    if (i <= 0) return "Omni arrow";
    if (i <= omniPointerArtCount) return omniPointerArts[i - 1].name;
    const int j = i - 1 - omniPointerArtCount;
    if (j >= int(omniPtrPictures.size())) return "Omni arrow";
    std::string n = omniPtrPictures[j].file;
    n = n.substr(0, n.size() - 4);
    if (const size_t at = n.rfind('@'); at != std::string::npos && omniPtrPictures[j].hotX >= 0) n = n.substr(0, at);
    return "Picture: " + n;
}
static bool omniPtrIsPicture() { return omniPtrStyleIndex() > omniPointerArtCount; }
static float omniPtrSizeFactor() { omniFxLoad(); return omniPtrSizes[std::clamp(omniFxSet.psize, 0, omniPtrSizeCount - 1)] / 100.f; }
static uint8_t omniPtrAlpha() { omniFxLoad(); return uint8_t(omniPtrOpacities[std::clamp(omniFxSet.popacity, 0, omniPtrOpacityCount - 1)] * 255 / 100); }
// Everything the sprite depends on (opacity is applied when drawing).
static uint64_t omniPtrSignature(double scale)
{
    omniFxLoad();
    uint64_t h = std::hash<std::string>()(omniFxSet.pstyle);
    h ^= (uint64_t(std::clamp(omniFxSet.psize, 0, 255)) << 1) ^ (uint64_t(std::clamp(omniFxSet.pcolour, 0, 255)) << 9)
        ^ (uint64_t(omniFxSet.poutline) << 17) ^ (uint64_t(uint32_t(scale * 1000 + 0.5)) << 20);
    return h ? h : 1;
}

static SDL_Surface* omniPtrSurface(const uint32_t* argb, int w, int h)
{
    SDL_Surface* s = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!s) return nullptr;
    for (int y = 0; y < h; ++y) memcpy(static_cast<uint8_t*>(s->pixels) + size_t(y) * s->pitch, argb + size_t(y) * w, size_t(w) * 4);
    SDL_SetSurfaceBlendMode(s, SDL_BLENDMODE_BLEND);
    return s;
}
// A user's picture: PNG, at most 512x512 and 2 MiB, decoded with libpng's simplified reader into straight RGBA.
static bool omniPtrLoadPicture(const std::string& file, std::vector<uint8_t>& rgba, int& w, int& h, std::string& why)
{
#if defined(PNG_SIMPLIFIED_READ_SUPPORTED)
    const std::string path = omniData("pointers") + "/" + file;
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) { why = "cannot open"; return false; }
    std::vector<uint8_t> bytes;
    uint8_t chunk[16384];
    size_t n;
    while ((n = fread(chunk, 1, sizeof(chunk), f)) > 0) {
        bytes.insert(bytes.end(), chunk, chunk + n);
        if (long(bytes.size()) > omniPtrPictureMaxBytes) { fclose(f); why = "larger than 2 MiB"; return false; }
    }
    fclose(f);
    png_image image;
    memset(&image, 0, sizeof(image));
    image.version = PNG_IMAGE_VERSION;
    if (!png_image_begin_read_from_memory(&image, bytes.data(), bytes.size())) { why = "not a readable PNG"; return false; }
    if (!image.width || !image.height || image.width > unsigned(omniPtrPictureMaxSide) || image.height > unsigned(omniPtrPictureMaxSide)) {
        png_image_free(&image); why = "larger than 512x512"; return false;
    }
    image.format = PNG_FORMAT_RGBA;
    rgba.assign(PNG_IMAGE_SIZE(image), 0);
    if (!png_image_finish_read(&image, nullptr, rgba.data(), 0, nullptr)) { png_image_free(&image); why = "PNG decode failed"; return false; }
    w = int(image.width); h = int(image.height);
    png_image_free(&image);
    return true;
#else
    (void)file; (void)rgba; (void)w; (void)h; why = "PNG reading not available"; return false;
#endif
}

// The pointer sprite for the current settings at this display scale (straight-alpha ARGB8888, caller frees),
// with the hotspot (arrow tip, finger tip, centre) in sprite pixels. Never fails: falls back to Omni's arrow.
static SDL_Surface* omniPtrBuildSprite(double scale, int* hotX, int* hotY)
{
    omniFxLoad();
    const float size = omniPtrSizeFactor(), unit = float(scale) * size;
    const int style = omniPtrStyleIndex();
    const uint8_t* body = omniPtrColours[std::clamp(omniFxSet.pcolour, 0, omniPtrColourCount - 1)];
    uint8_t rim[3];
    omniPtrContrast(body, rim);
    if (style >= 1 && style <= omniPointerArtCount) {
        const OmniPointerArt& art = omniPointerArts[style - 1];
        const size_t plane = size_t(omniPointerArtSize) * omniPointerArtSize;
        std::vector<uint8_t> planes(2 * plane);
        uLongf n = uLongf(planes.size());
        if (uncompress(planes.data(), &n, art.z, art.zlen) == Z_OK && n == planes.size()) {
            const int t = std::max(2, int((art.crosshair ? omniPtrCrosshairBase : omniPtrCursorBase) * unit + 0.5f));
            OmniPtrPaint paint;
            memcpy(paint.fill, body, 3); memcpy(paint.edge, rim, 3);
            paint.outline = omniFxSet.poutline; paint.unit = unit;
            const OmniPtrImage img = omniPtrRender(planes.data(), planes.data() + plane, nullptr, omniPointerArtSize, omniPointerArtSize, art.hotX, art.hotY, t, t, paint);
            if (SDL_Surface* s = omniPtrSurface(img.argb.data(), img.w, img.h)) { *hotX = img.hotX; *hotY = img.hotY; return s; }
        } else fprintf(stderr, "pointer: art '%s' failed to inflate; using Omni's arrow\n", art.name);
    } else if (style > omniPointerArtCount) {
        const OmniPtrPicture& pic = omniPtrPictures[style - 1 - omniPointerArtCount];
        std::vector<uint8_t> rgba; int w = 0, h = 0; std::string why;
        if (omniPtrLoadPicture(pic.file, rgba, w, h, why)) {
            const float k = omniPtrPictureBase * unit / float(std::max(w, h));
            const int tw = std::max(2, int(w * k + 0.5f)), th = std::max(2, int(h * k + 0.5f));
            const float hx = pic.hotX >= 0 ? float(std::min(pic.hotX, w - 1)) : w / 2.f, hy = pic.hotY >= 0 ? float(std::min(pic.hotY, h - 1)) : h / 2.f;
            OmniPtrPaint paint; paint.unit = unit; paint.outline = false;
            const OmniPtrImage img = omniPtrRender(nullptr, nullptr, rgba.data(), w, h, hx, hy, tw, th, paint);
            if (SDL_Surface* s = omniPtrSurface(img.argb.data(), img.w, img.h)) { *hotX = img.hotX; *hotY = img.hotY; return s; }
        } else fprintf(stderr, "pointer: picture '%s' %s; using Omni's arrow\n", pic.file.c_str(), why.c_str());
    }
    const uint8_t white[3] = { 255, 255, 255 }, dark[3] = { 16, 20, 28 };
    const bool own = style == 0;   // anything that failed above falls back to exactly the default arrow
    int w = 0, h = 0;
    const auto argb = omniPtrOmniArrow(float(scale), own ? size : 1.f, own ? body : white, own ? rim : dark, own ? omniFxSet.poutline : true, w, h, *hotX, *hotY);
    return omniPtrSurface(argb.data(), w, h);
}

// --- Browser settings rows (OmniBrowserSettings.h) -------------------------------------------------
static std::string omniPtrPercent(int v) { return std::to_string(v) + "%"; }
static void omniPtrSettingsRows(OmniFxPanel& p)
{
    if (!omniPtrPicturesScanned) omniPtrScanPictures();
    auto add = [&](int id, const char* label, std::string value) { OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.stepper = true; p.rows.push_back(r); };
    const int style = omniPtrStyleIndex(), count = omniPtrStyleCount();
    const bool picture = style > omniPointerArtCount;
    add(omniFxSetPtrStyle, "Pointer style", omniPtrStyleName(style) + "  (" + std::to_string(style + 1) + " of " + std::to_string(count) + ")");
    add(omniFxSetPtrSize, "Pointer size", omniPtrPercent(omniPtrSizes[std::clamp(omniFxSet.psize, 0, omniPtrSizeCount - 1)]));
    add(omniFxSetPtrColour, "Pointer colour", picture ? std::string("Picture's own") : omniPtrColourNames[std::clamp(omniFxSet.pcolour, 0, omniPtrColourCount - 1)]);
    add(omniFxSetPtrOutline, "Pointer outline", picture ? std::string("Picture's own") : omniFxSet.poutline ? "On (contrasting)" : "Off");
    add(omniFxSetPtrOpacity, "Pointer opacity", omniPtrPercent(omniPtrOpacities[std::clamp(omniFxSet.popacity, 0, omniPtrOpacityCount - 1)]));
}
// D-pad left/right step, Cross steps forward (wrapping), Triangle resets the row. The pointer itself is the live preview.
static bool omniPtrSettingsInput(int id, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A, reset = b == SDL_CONTROLLER_BUTTON_Y;
    const int dir = left ? -1 : (right || a) ? 1 : 0;
    if (!dir && !reset) return false;
    const bool picture = omniPtrIsPicture();
    switch (id) {
    case omniFxSetPtrStyle: {
        omniPtrScanPictures();   // pick up pictures copied in since the panel opened
        const int count = omniPtrStyleCount(), at = omniPtrStyleIndex();
        omniFxSet.pstyle = reset ? std::string("omni") : omniPtrStyleKey((at + dir + count) % count);
        break;
    }
    case omniFxSetPtrSize: omniFxSet.psize = reset ? omniPtrSizeDefault : a ? (std::clamp(omniFxSet.psize, 0, omniPtrSizeCount - 1) + 1) % omniPtrSizeCount : std::clamp(omniFxSet.psize + dir, 0, omniPtrSizeCount - 1); break;
    case omniFxSetPtrColour:
        if (picture) { notice("A picture pointer keeps its own colours"); return true; }
        omniFxSet.pcolour = reset ? 0 : (std::clamp(omniFxSet.pcolour, 0, omniPtrColourCount - 1) + dir + omniPtrColourCount) % omniPtrColourCount; break;
    case omniFxSetPtrOutline:
        if (picture) { notice("A picture pointer keeps its own outline"); return true; }
        omniFxSet.poutline = reset ? true : !omniFxSet.poutline; break;
    case omniFxSetPtrOpacity:   // right = a higher percentage (more solid); Cross cycles down and wraps
        omniFxSet.popacity = reset ? 0 : a ? (std::clamp(omniFxSet.popacity, 0, omniPtrOpacityCount - 1) + 1) % omniPtrOpacityCount : std::clamp(omniFxSet.popacity - dir, 0, omniPtrOpacityCount - 1); break;
    default: return false;
    }
    omniFxSave();
    return true;
}
