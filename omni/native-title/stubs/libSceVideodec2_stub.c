/* omni-native-s0: link stub for libSceVideodec2 (the native SDK has none). Only the names
 * matter: ps5-native-tool turns them into imports of the system module; nothing here runs on
 * the console. Functions used by media/OmniHwBackend.cpp (SYM list). SPDX-License-Identifier: GPL-3.0-or-later */
int sceVideodec2QueryComputeMemoryInfo(void) { return 0; }
int sceVideodec2AllocateComputeQueue(void) { return 0; }
int sceVideodec2ReleaseComputeQueue(void) { return 0; }
int sceVideodec2QueryDecoderMemoryInfo(void) { return 0; }
int sceVideodec2CreateDecoder(void) { return 0; }
int sceVideodec2DeleteDecoder(void) { return 0; }
int sceVideodec2Reset(void) { return 0; }
int sceVideodec2Decode(void) { return 0; }
int sceVideodec2Flush(void) { return 0; }
