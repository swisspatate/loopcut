// SPDX-License-Identifier: MIT
#pragma once
#include <cmath>
namespace CryptoNyanMechanismRules {
inline bool Valid(int Kind, int Element, double Strength) {
    return Kind>=0 && Kind<6 && Element>=0 && Element<6 && std::isfinite(Strength) && Strength>=.1 && Strength<=2000;
}
inline bool Activate(int Kind, int Required, int Received, bool AlreadyActive) {
    return !AlreadyActive && (Kind==0 || Kind==1) && Required>=0 && Required<6 && Required==Received;
}
inline double Gravity(double Strength) { return std::fmax(.1, std::fmin(2., Strength)); }
inline double WindImpulse(double Strength, double Delta) {
    return std::isfinite(Delta) && Delta>0 ? std::fmin(2000., std::fmax(0., Strength))*std::fmin(.1, Delta) : 0;
}
}
