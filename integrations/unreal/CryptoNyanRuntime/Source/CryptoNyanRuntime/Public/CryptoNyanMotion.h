// SPDX-License-Identifier: MIT
#pragma once
#include <cmath>

// Independent, engine-free implementation, also compiled by the portable test suite.
namespace CryptoNyanMotion
{
inline double Triangle(double Elapsed, double Period, double Phase)
{
    if (!std::isfinite(Elapsed) || !std::isfinite(Period) || !std::isfinite(Phase) || Period <= 0.0)
        return 0.0;
    double Q = std::fmod(Elapsed + Phase, Period) / Period;
    if (Q < 0.0) Q += 1.0;
    return Q < 0.75 ? 1.0 - 4.0 * std::abs(Q - 0.25) : 4.0 * Q - 4.0;
}
}
