// OMNI_AUDIO_RELAY_V1: all audio output from the UI (big-app) process. SPDX-License-Identifier: GPL-3.0-or-later
//
// Why: on the console (v83) the WebProcess's SDL audio device took loud PCM in real time
// (callbackBytes ~5000 ms per 5 s, outPeak ~20000, device playing) and the TV stayed silent,
// for MSE and plain <video> alike; a homebrew app that opens SDL audio in its own main process
// is heard. The WebProcess is a child started by Omni's launcher: the system evidently drops
// audio output from it even though sceAudioOutOpen/Output succeed.
//
// What: the players write decoded PCM (48 kHz s16 stereo) into an OmniAudioRing in shared
// memory; the UI process (this file's relay, started by OmniMain) opens one SDL device and mixes
// every active ring in its callback, with each ring's gain, and publishes how far it read
// (and when, and its device buffer), so the player's audio-master clock (AudioRing::heard)
// works as it does with a local device. Transport as the decode service's (OmniHwProtocol.h):
// AF_UNIX socket pairs made by the relay, a rendezvous file (<OMNI_HW_DIR>/audio), claim files,
// the WebProcess copying descriptors out with omni_remote_dup(); one channel and one shared
// ring per player. The relay never waits on a WebProcess: a ring of a process that is gone is
// dropped when its socket closes (under the device lock), the callback only reads shared memory.
//
// Kill switch: /data/omni/audio-relay-disabled.flag (host: OMNI_AUDIO_RELAY=1 turns it on).
// Players then open SDL audio in the WebProcess as before.
#pragma once
#include "OmniAudioRing.h"
#include <cstdint>
#include <memory>
#include <string>

struct SDL_AudioSpec;

namespace OmniMedia::Audio {

bool relayFlagEnabled();

// ---- UI process -----------------------------------------------------------------------------
// Opens the audio device (48 kHz s16 stereo, 1024 frames, SDL converts to the driver's format),
// starts the relay thread and publishes the rendezvous. Call from the main thread before the
// shell runs (SDL's subsystem init is not thread-safe). False: no relay (detail says why).
bool relayStart(std::string& detail);
// Stops the thread and drops every ring; closes the device unless SDL's audio was quit already
// (SDL_Quit closes it). fromSignal: no SDL call, no lock.
void relayStop(bool fromSignal = false);
struct RelayStats {
    bool running = false, deviceOpen = false;
    unsigned rings = 0, playing = 0;
    uint64_t framesMixed = 0, callbacks = 0;
};
RelayStats relayStats();
void relayHudEnable(bool);
// Current active relay rings; -1 means no active ring, not a zero-underrun claim.
int64_t relayHudUnderruns();

// ---- WebProcess -----------------------------------------------------------------------------
// A player's audio output: an SDL device in this process (as before the relay), or a ring the
// relay plays. The calls mirror the SDL ones the players made.
class Output {
public:
    // The relay (null: unavailable, or the kill switch; `why` says which). Waits up to 0.6 s for a
    // channel being recycled, and at most ~1.5 s for the relay's answer.
    static std::unique_ptr<Output> openRelay(std::string& why);
    // SDL_OpenAudioDevice(nullptr, 0, wanted, actual, 0) in this process (null: failed).
    static std::unique_ptr<Output> openSdl(const SDL_AudioSpec* wanted, SDL_AudioSpec* actual);
    ~Output();
    Output(const Output&) = delete;
    Output& operator=(const Output&) = delete;
    bool relay() const { return relayFd_ >= 0; }
    // Relay: a producer view of the shared ring for the player's own writes (V5's path); the
    // memory stays this object's, so the view must not be used after this object is gone.
    std::unique_ptr<AudioRing> makeRingView();
    void pause(bool paused);                // SDL_PauseAudioDevice
    bool playing() const;                   // SDL_GetAudioDeviceStatus == PLAYING (relay: not paused and its device calls back)
    const char* statusName() const;
    void lock();                            // SDL_LockAudioDevice (relay: nothing; clear() is a request)
    void unlock();
    uint32_t queuedBytes() const;           // SDL_GetQueuedAudioSize (relay: what the ring holds)
    void clearQueued();                     // SDL_ClearQueuedAudio (relay: AudioRing::clear)
    int queue(const void* data, uint32_t bytes);   // SDL_QueueAudio (relay: into the ring; -1 no room)
    int deviceFrames() const;               // the device's buffer, frames
    unsigned id() const;                    // SDL device id (relay: 1000 + channel), for logs
    std::string describe() const;
private:
    Output() = default;
    static std::unique_ptr<Output> tryOpenRelay(std::string& why, bool& recycling);
    unsigned sdl_ = 0;
    int relayFd_ = -1, channel_ = -1;
    void* shm_ = nullptr;
    size_t shmSize_ = 0;
    std::unique_ptr<AudioRing> view_;       // relay: this object's producer view (queue/clearQueued/pause)
    double queuedMedia_ = 0;                // relay: media time for queue()d PCM
    uint32_t deviceFrames_ = 1024;
};

}
