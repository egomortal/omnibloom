# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled.

Uses only CSS `object-fit` ([CSS Images 3](https://www.w3.org/TR/css-images-3/#the-object-fit)) and `transform: scale()` ([CSS Transforms 1](https://www.w3.org/TR/css-transforms-1/)) on page `<video>` elements, set from a user-level stylesheet keyed on a `data-omni-fit` attribute. Checked 2026-11-16.

Modes: Fit (the page's own look; nothing applied), Fill (`object-fit: cover`, centred crop), Stretch (`object-fit: fill`), Zoom 1.1 / 1.2 / 1.33 (`object-fit: contain` + `scale()` about the centre, after any transform the page already had). Videos under 200 x 112 CSS px are left alone unless full screen. Work happens on media events (`loadedmetadata`, `resize`), window resize and full-screen changes, and a MutationObserver that only looks for added videos (one 250 ms debounce per burst). No polling.

## Hardware video plane

Omni's players (engine/entry/OmniMSEPlayer.cpp and OmniProgressivePlayer.cpp, `holeGeometry`) report the rect `RenderVideo` paints the picture in (`computePaintRectForObjectViewBox(videoBox())`, so object-fit is included) mapped through `localToAbsoluteQuad` (so CSS transforms are included). A scale stays rectilinear, so the video stays eligible; the shell (engine/media/OmniHwService.cpp) scales the whole frame into that rect and shows it only where the page left its transparent hole, which WebKit clips to the element and its overflow-clipping ancestors, so Fill and Zoom crop correctly on the plane. The stylesheet never sets opacity, filter, mask, clip-path, blend modes, rotation or skew (any of those takes a video off the plane).

The one catch: the shell refuses a rect over 4096 px on a side or over 3840 x 2160 pixels (OmniHwProtocol.h), and the video then falls back to software painting. With "Limit zoom so video stays on the hardware video plane" on (the default), Fill and Zoom are held back to the largest scale that still fits, computed with `devicePixelRatio`, and the panel says so. A full-screen video on a 4K root view is already at the pixel cap, so there Fill and Zoom are held back to Fit.

## Stored data

With "Remember for this site" on, one entry per site: a hash of the host name (www. dropped; the host itself is not stored) holding the mode and when it was chosen. At most 300 sites; the oldest are dropped. Turning the switch off removes that site's entry. Private tabs run this add-on (private_safe) but Omni refuses add-on storage writes there ("error: private tab"), so a choice made in a private tab lasts for that page only; saved choices are still read.

## Controls

Alt+Shift+F opens the panel (or, when the `<video>` element itself is full screen and nothing can be drawn over it, steps to the next mode with a toast). Switching the add-on on from the quick switch on a page with a video opens the panel. A "Video fit" button shows for 5 s when a large video starts (once per video; can be turned off). The panel's buttons are pointer targets (left stick + Cross); a keyboard's arrows move between them and Escape / Circle closes it.
