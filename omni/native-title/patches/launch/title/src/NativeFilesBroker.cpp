// OMNI_FILES_BROKER_V1 (omni-native-s1b): tells the shell (OmniFilesBroker.h, a weak reference) that
// it runs as the native title, so USB drives and extended storage go through the omni-files broker.
// The big-app engine has no such definition: the weak reference stays null and nothing changes there.
extern "C" int omni_native_title_active(void) { return 1; }
