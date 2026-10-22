// SPDX-License-Identifier: MIT
#pragma once
#include <array>
#include <cmath>
#include <cstdint>

// Engine-free policy shared by the runtime and portable executable tests.
namespace CryptoNyanFeedbackRules {
constexpr int Channels=10; // Eight explicitly mapped feet, jump, landing.
struct CueKey { int Kind; std::uintptr_t Material; };
inline int Select(const CueKey* Cues, int Count, int Kind, std::uintptr_t Material) {
    if (!Cues || Count<1 || Count>32 || Kind<0 || Kind>2) return -1;
    int Fallback=-1;
    for (int I=0; I<Count; ++I) {
        if (Cues[I].Kind!=Kind) continue;
        if (Cues[I].Material && Cues[I].Material==Material) return I;
        if (!Cues[I].Material) Fallback=I;
    }
    return Fallback;
}
inline double Intensity(double Speed, double Reference) {
    if (!std::isfinite(Speed) || !std::isfinite(Reference) || Speed<0 || Reference<=0) return 0;
    return std::fmin(1.,Speed/Reference);
}
inline int Variant(int Count, int Previous, std::uint32_t Roll) {
    if (Count<1 || Count>8) return -1;
    if (Count==1) return 0;
    if (Previous<0 || Previous>=Count) return int(Roll%std::uint32_t(Count));
    const int Pick=int(Roll%std::uint32_t(Count-1));
    return Pick>=Previous ? Pick+1 : Pick;
}
struct Gate {
    std::array<double,Channels> Last;
    double Tokens=8, Updated=-1;
    Gate() { Last.fill(-1); }
    bool Admit(int Channel, double Now, double Cooldown) {
        if (Channel<0 || Channel>=Channels || !std::isfinite(Now) || Now<0 ||
            !std::isfinite(Cooldown) || Cooldown<.04-1e-8 || Cooldown>1 ||
            (Updated>=0 && Now<Updated) || (Last[Channel]>=0 && Now-Last[Channel]<Cooldown) ||
            (Channel<8 && Last[9]>=0 && Now-Last[9]<Cooldown)) return false;
        const double Available=Updated<0 ? 8 : std::fmin(8.,Tokens+(Now-Updated)*24.);
        if (Available<1) return false;
        Tokens=Available-1; Updated=Now; Last[Channel]=Now;
        return true;
    }
};
}
