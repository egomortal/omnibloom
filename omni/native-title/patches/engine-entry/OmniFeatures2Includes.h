// OMNI_FEATURES_V2: WebKit C API headers used by the passwords, file picker and site permission
// features (OmniPasswords.h, OmniFilePicker.h, OmniPermissions.h). Included once near the top of
// OmniBrowser.cpp, outside its anonymous namespace.
#pragma once
#include <WebKit/WKOpenPanelParametersRef.h>
#include <WebKit/WKOpenPanelResultListener.h>
#include <WebKit/WKGeolocationPermissionRequest.h>
#include <WebKit/WKNotificationPermissionRequest.h>
#include <WebKit/WKUserMediaPermissionRequest.h>
#include <WebKit/WKScriptMessageRef.h>
#include <WebKit/WKUserContentControllerRef.h>
#include <WebKit/WKUserScriptRef.h>
#include <WebKit/WKSecurityOriginRef.h>
#include <WebKit/WKFrameInfoRef.h>
#include <WebKit/WKArray.h>
#include <WebKit/WKMutableArray.h>
#include <WebKit/WKString.h>
#include <WebKit/WKURL.h>
#include <dirent.h>
#include <sys/stat.h>
#include <map>
#include <vector>
#include <string>
// OMNI_FILES_BROKER_V1: loopback client for the native title's USB broker (OmniFilesBroker.h)
#include <sys/socket.h>
#include <sys/time.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <atomic>
// Defined only in the native title (outputs/omni-native-s1b/src/NativeFilesBroker.cpp); null in the big-app.
extern "C" int omni_native_title_active(void) __attribute__((weak));
// OMNI_VAULT_V2: encrypted password/2FA storage (needs OpenSSL declarations at namespace scope)
#include "OmniVault.h"
