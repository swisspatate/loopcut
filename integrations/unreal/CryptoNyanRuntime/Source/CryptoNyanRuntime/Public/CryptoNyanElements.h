// SPDX-License-Identifier: MIT
#pragma once
#include <cmath>

// Engine-free gameplay rules: used by the UE components and portable C++ tests.
namespace CryptoNyanElements
{
enum class Element { Fire, Ice, Earth, Wind, Water, Electric };
struct Traits { bool Flammable=false, Freezable=false, Conductive=false, Movable=false; };
struct State { bool Wet=false, Frozen=false, Burned=false, Charged=false, Raised=false, Gust=false; };
inline State React(State S, Traits T, Element E)
{
    switch (E)
    {
    case Element::Water: S.Wet=true; break;
    case Element::Ice: if (T.Freezable && S.Wet && !S.Burned) S.Frozen=true; break;
    case Element::Fire:
        if (S.Frozen) { S.Frozen=false; S.Wet=true; }
        else if (S.Wet) S.Wet=false;
        else if (T.Flammable) S.Burned=true;
        break;
    case Element::Electric: if (T.Conductive || S.Wet) S.Charged=true; break;
    case Element::Earth: if (T.Movable && !S.Burned) S.Raised=true; break;
    case Element::Wind: if (T.Movable && !S.Burned) S.Gust=true; break;
    }
    return S;
}
inline bool CanSpend(double Now, double ReadyAt, double Energy, double Cost, double Cooldown)
{
    return std::isfinite(Now) && std::isfinite(ReadyAt) && std::isfinite(Energy) &&
           std::isfinite(Cost) && std::isfinite(Cooldown) && Now>=ReadyAt && Energy>=Cost &&
           Cost>0 && Cost<=100 && Cooldown>=0.05 && Cooldown<=60;
}
struct Point { double X, Y, Z, Scale; };
inline Point Particle(int Index, int Count, double Age, double Duration)
{
    if (Count<1 || Count>128 || Index<0 || Index>=Count || !std::isfinite(Age) ||
        !std::isfinite(Duration) || Duration<=0 || Age<0 || Age>=Duration) return {0,0,0,0};
    const double T=Age/Duration, Angle=Index*6.283185307179586/Count;
    const double Radius=15+120*T;
    return {std::cos(Angle)*Radius, std::sin(Angle)*Radius, 60*T, .08*(1-T)};
}
}
