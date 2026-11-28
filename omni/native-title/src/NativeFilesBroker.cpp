// NativeFilesBroker.cpp - one switch that tells Omni's browser code "you are the PS5 title".
// Used by: the title build only (build.py compiles it into eboot.bin). The engine child never links it.
//
// OMNI_FILES_BROKER_V1 (omni-native-s1b): tells the shell (OmniFilesBroker.h, a weak reference) that
// it runs as the native title, so USB drives and extended storage go through the omni-files broker.
// The big-app engine has no such definition: the weak reference stays null and nothing changes there.
extern "C" int omni_native_title_active(void) { return 1; }
