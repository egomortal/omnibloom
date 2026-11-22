// OMNI_PAINT_HOLD_PROPOSAL: presentation only; renderer continues normally.
static bool omniPaintHoldEligible(const std::string& url)
{
    for (const char* prefix : { "https://www.youtube.com/", "https://m.youtube.com/", "https://youtube.com/" })
        if (url.rfind(prefix, 0) == 0) return true;
    return false;
}
static void omniPaintHoldBegin(Tab& tab, WKPageRef page)
{
    static uint64_t sequence = 0;
    if (sequence == UINT64_MAX) { tab.omniPaintHold.cancel(); return; }
    auto value = adoptWK(WKPageCopyActiveURL(page));
    const std::string url = value ? OmniTest::toStd(adoptWK(WKURLCopyString(value.get())).get()) : std::string();
    tab.omniPaintHold.begin(++sequence, SDL_GetTicks(), !omniTestMode() && !tab.omniPrivate
        && !access("/data/omni/paint-hold-experimental.flag", F_OK) && omniPaintHoldEligible(url));
    omniShellDirty = true;
}
static void omniPaintHoldTick()
{
    Tab* tab = active();
    if (!tab || !tab->omniPaintHold.active) return;
    const bool wasHolding = tab->omniPaintHold.active;
    const uint32_t now = SDL_GetTicks();
    auto value = adoptWK(WKPageCopyActiveURL(tab->page));
    const std::string url = value ? OmniTest::toStd(adoptWK(WKURLCopyString(value.get())).get()) : std::string();
    if (tab->crashed || !tab->message.empty() || tab->omniPrivate || !omniPaintHoldEligible(url)) tab->omniPaintHold.cancel();
    if (!tab->omniPaintHold.holding(now)) { if (wasHolding) omniShellDirty = true; return; }
    if (!tab->omniPaintHold.probe(now)) return;
    static const char source[] = R"OMNIPH((()=>{if(location.protocol!=='https:'||!['www.youtube.com','m.youtube.com','youtube.com'].includes(location.hostname))return 'release';
const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>8&&r.height>8&&r.bottom>0&&r.top<innerHeight&&s.visibility!=='hidden'&&s.display!=='none'&&Number(s.opacity)>0;};
if(Array.from(document.querySelectorAll('dialog[open],[role="dialog"],[role="alertdialog"],form[action*="consent"],iframe[src*="recaptcha"]')).slice(0,20).some(visible))return 'release';
const video=document.querySelector('video');if(video&&visible(video)&&video.readyState>=2)return 'ready';
const cards=document.querySelectorAll('ytd-rich-item-renderer,ytd-video-renderer,ytm-video-with-context-renderer');let count=0;
for(let i=0;i<Math.min(cards.length,24);i++){const card=cards[i],img=card.querySelector('img'),title=card.querySelector('#video-title,[aria-label]');if(visible(card)&&img&&img.complete&&img.naturalWidth>0&&visible(img)&&title&&title.textContent.trim().length>0&&++count>=2)return 'ready';}
return 'wait';})())OMNIPH";
    auto script = adoptWK(WKStringCreateWithUTF8CString(source));
    const auto epoch = tab->omniPaintHold.epoch;
    WKPageEvaluateJavaScriptInMainFrame(tab->page, script.get(), reinterpret_cast<void*>(static_cast<uintptr_t>(epoch)),
        [](WKTypeRef result, WKErrorRef error, void* opaque) {
            const auto epoch = static_cast<uint64_t>(reinterpret_cast<uintptr_t>(opaque));
            for (auto& tab : tabs) {
                if (tab->omniPaintHold.epoch != epoch) continue;
                const std::string answer = !error && result && WKGetTypeID(result) == WKStringGetTypeID()
                    ? OmniTest::toStd(static_cast<WKStringRef>(result)) : std::string();
                tab->omniPaintHold.reply(epoch, error || answer == "ready" || answer == "release");
                omniShellDirty = true;
                break;
            }
        });
}

