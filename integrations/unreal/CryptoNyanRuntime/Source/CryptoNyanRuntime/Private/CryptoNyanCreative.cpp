// SPDX-License-Identifier: MIT
#include "CryptoNyanCreative.h"
#include "Components/BoxComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Engine/OverlapResult.h"
#include "GameFramework/Character.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraComponent.h"
#include "UObject/ConstructorHelpers.h"
#include "TimerManager.h"

namespace
{
FLinearColor ElementColor(ECryptoNyanElement E)
{
    switch (E) {
    case ECryptoNyanElement::Fire: return FLinearColor(1,.12,.01);
    case ECryptoNyanElement::Ice: return FLinearColor(.1,.65,1);
    case ECryptoNyanElement::Earth: return FLinearColor(.4,.2,.06);
    case ECryptoNyanElement::Wind: return FLinearColor(.6,1,.8);
    case ECryptoNyanElement::Water: return FLinearColor(.02,.3,.8);
    default: return FLinearColor(.7,.15,1);
    }
}
bool ValidElement(ECryptoNyanElement E) { return uint8(E)<=uint8(ECryptoNyanElement::Electric); }
}

ACryptoNyanElementSurface::ACryptoNyanElementSurface()
{
    Collision=CreateDefaultSubobject<UBoxComponent>(TEXT("Collision"));
    SetRootComponent(Collision);
    Collision->SetBoxExtent(FVector(50));
    Collision->SetCollisionProfileName(TEXT("BlockAllDynamic"));
    Collision->SetMobility(EComponentMobility::Movable);
    Surface=CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Surface"));
    Surface->SetupAttachment(Collision);
    Surface->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Surface->SetMobility(EComponentMobility::Movable);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (Cube.Succeeded()) Surface->SetStaticMesh(Cube.Object);
}
void ACryptoNyanElementSurface::BeginPlay()
{
    Super::BeginPlay();
    Origin=GetActorLocation();
    ResetElements();
}
void ACryptoNyanElementSurface::ResetElements()
{
    if (!HasActorBegunPlay()) Origin=GetActorLocation();
    State={};
    State.Wet=InitiallyWet || Liquid;
    SetActorLocation(Origin, true);
    ApplyState();
}
void ACryptoNyanElementSurface::ApplyState()
{
    Wet=State.Wet; Frozen=State.Frozen; Burned=State.Burned; Charged=State.Charged; Raised=State.Raised;
    Surface->SetVisibility(!Burned);
    Collision->SetCollisionEnabled(Burned ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryAndPhysics);
    // Liquid remains queryable by powers, but the player's capsule can pass through it.
    Collision->SetCollisionResponseToChannel(ECC_Pawn,Liquid && !Frozen ? ECR_Ignore : ECR_Block);
    const ECryptoNyanElement Tint=Frozen ? ECryptoNyanElement::Ice : Charged ? ECryptoNyanElement::Electric :
        Wet ? ECryptoNyanElement::Water : ECryptoNyanElement::Earth;
    if (!DynamicMaterial) DynamicMaterial=Surface->CreateAndSetMaterialInstanceDynamic(0);
    if (DynamicMaterial) DynamicMaterial->SetVectorParameterValue(TEXT("Tint"), ElementColor(Tint));
}
bool ACryptoNyanElementSurface::ApplyElement(ECryptoNyanElement E, FVector Direction)
{
    if (!GetWorld() || GetNetMode()!=NM_Standalone || !ValidElement(E) || Direction.ContainsNaN()) return false;
    const auto Before=State;
    const FVector BeforeLocation=GetActorLocation();
    const CryptoNyanElements::Traits Traits{Flammable,Freezable,Conductive,Movable};
    State=CryptoNyanElements::React(State,Traits,static_cast<CryptoNyanElements::Element>(E));
    if (E==ECryptoNyanElement::Earth && State.Raised && FMath::IsFinite(RiseCm)) {
        FVector Target=GetActorLocation();
        Target.Z=Origin.Z+FMath::Clamp(RiseCm,0.f,500.f);
        SetActorLocation(Target,true);
    }
    if (E==ECryptoNyanElement::Wind && State.Gust)
        AddActorWorldOffset(Direction.GetSafeNormal()*150,true);
    ApplyState();
    const bool Changed=Before.Wet!=State.Wet || Before.Frozen!=State.Frozen || Before.Burned!=State.Burned ||
        Before.Charged!=State.Charged || Before.Raised!=State.Raised || Before.Gust!=State.Gust ||
        !BeforeLocation.Equals(GetActorLocation(),.1);
    if (Changed) OnElementChanged.Broadcast(E);
    return Changed;
}

ACryptoNyanElementEffect::ACryptoNyanElementEffect()
{
    PrimaryActorTick.bCanEverTick=true;
    Collision=CreateDefaultSubobject<USphereComponent>(TEXT("ProjectileCollision"));
    SetRootComponent(Collision);
    Collision->InitSphereRadius(12);
    Collision->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Collision->SetCollisionResponseToAllChannels(ECR_Block);
    Particles=CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Particles"));
    Particles->SetupAttachment(Collision);
    Particles->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Particles->SetCanEverAffectNavigation(false);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    if (Sphere.Succeeded()) Particles->SetStaticMesh(Sphere.Object);
}
void ACryptoNyanElementEffect::Start(ECryptoNyanElement E, ECryptoNyanPowerShape S, FVector Direction, float Radius, UMaterialInterface* Material)
{
    Element=E; Shape=S; ZoneRadius=Radius;
    Velocity=Direction.GetSafeNormal()*1500;
    Duration=(Shape==ECryptoNyanPowerShape::Projectile || Shape==ECryptoNyanPowerShape::Zone) ? 3.f : .6f;
    if (Material) {
        Particles->SetMaterial(0,Material);
        if (UMaterialInstanceDynamic* MID=Particles->CreateAndSetMaterialInstanceDynamic(0))
            MID->SetVectorParameterValue(TEXT("Tint"),ElementColor(Element));
    }
    if (Shape==ECryptoNyanPowerShape::Projectile) {
        Collision->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        if (GetOwner()) Collision->IgnoreActorWhenMoving(GetOwner(),true);
    }
    for (int I=0; I<24; ++I) Particles->AddInstance(FTransform(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector));
    SetLifeSpan(Duration+.1f);
    if (Shape==ECryptoNyanPowerShape::Impact || Shape==ECryptoNyanPowerShape::Zone) AffectNearby();
}
void ACryptoNyanElementEffect::AffectNearby()
{
    if (!GetWorld()) return;
    TArray<FOverlapResult> Hits;
    FCollisionObjectQueryParams Objects;
    Objects.AddObjectTypesToQuery(ECC_WorldStatic);
    Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
    FCollisionQueryParams Params;
    Params.AddIgnoredActor(this);
    if (GetOwner()) Params.AddIgnoredActor(GetOwner());
    GetWorld()->OverlapMultiByObjectType(Hits,GetActorLocation(),FQuat::Identity,Objects,
        FCollisionShape::MakeSphere(ZoneRadius),Params);
    for (const FOverlapResult& Hit: Hits) {
        if (Affected.Num()>=64) break;
        if (auto* Target=Cast<ACryptoNyanElementSurface>(Hit.GetActor())) {
            if (!Affected.Contains(TWeakObjectPtr<AActor>(Target))) {
                Affected.Add(TWeakObjectPtr<AActor>(Target));
                Target->ApplyElement(Element,(Target->GetActorLocation()-GetActorLocation()).GetSafeNormal());
            }
        }
    }
}
void ACryptoNyanElementEffect::Tick(float Delta)
{
    Super::Tick(Delta);
    if (!FMath::IsFinite(Delta) || Delta<0) return;
    Age+=Delta;
    if (Age>=Duration) { Destroy(); return; }
    if (Shape==ECryptoNyanPowerShape::Projectile) {
        FHitResult Hit;
        AddActorWorldOffset(Velocity*Delta,true,&Hit);
        if (Hit.bBlockingHit) {
            if (auto* Target=Cast<ACryptoNyanElementSurface>(Hit.GetActor())) Target->ApplyElement(Element,Velocity.GetSafeNormal());
            Destroy(); return;
        }
    }
    if (Shape==ECryptoNyanPowerShape::Zone && Age>=NextPulse) { AffectNearby(); NextPulse=Age+.25f; }
    for (int I=0; I<24; ++I) {
        const auto P=CryptoNyanElements::Particle(I,24,Age,Duration);
        const double Spread=Shape==ECryptoNyanPowerShape::Zone ? ZoneRadius/135.0 : Shape==ECryptoNyanPowerShape::Projectile ? .15 : 1;
        Particles->UpdateInstanceTransform(I,FTransform(FQuat::Identity,FVector(P.X*Spread,P.Y*Spread,P.Z*Spread),FVector(P.Scale)),false,I==23,true);
    }
}

UCryptoNyanPowerComponent::UCryptoNyanPowerComponent() { PrimaryComponentTick.bCanEverTick=true; }
void UCryptoNyanPowerComponent::TickComponent(float Delta,ELevelTick TickType,FActorComponentTickFunction* Function)
{
    Super::TickComponent(Delta,TickType,Function);
    if (FMath::IsFinite(Delta) && Delta>0) Energy=FMath::Clamp(Energy+Delta*8,0.f,100.f);
}
bool UCryptoNyanPowerComponent::ActivatePower(ECryptoNyanPowerShape Shape,FVector Direction)
{
    AActor* Actor=GetOwner();
    if (!Actor || !GetWorld() || Actor->GetNetMode()!=NM_Standalone || !ValidElement(SelectedElement) ||
        uint8(Shape)>uint8(ECryptoNyanPowerShape::Zone) || Direction.ContainsNaN() || Direction.IsNearlyZero() ||
        !FMath::IsFinite(RadiusCm) || RadiusCm<25 || RadiusCm>1000 ||
        !FMath::IsFinite(DashSpeed) || DashSpeed<100 || DashSpeed>2000 ||
        !CryptoNyanElements::CanSpend(GetWorld()->GetTimeSeconds(),ReadyAt,Energy,Cost,Cooldown)) return false;
    ACharacter* Character=Cast<ACharacter>(Actor);
    if (Shape==ECryptoNyanPowerShape::Dash && !Character) return false;
    Direction=Direction.GetSafeNormal();
    FActorSpawnParameters Params;
    Params.Owner=Actor;
    Params.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    const FVector Position=Actor->GetActorLocation()+Direction*(Shape==ECryptoNyanPowerShape::Projectile ? 80.f : 0.f);
    auto* FX=GetWorld()->SpawnActor<ACryptoNyanElementEffect>(Position,FRotator::ZeroRotator,Params);
    if (!FX) return false;
    FX->Start(SelectedElement,Shape,Direction,RadiusCm,EffectMaterial);
    if (Character && Shape==ECryptoNyanPowerShape::Dash) Character->LaunchCharacter(Direction*DashSpeed,true,false);
    Energy-=Cost; ReadyAt=GetWorld()->GetTimeSeconds()+Cooldown;
    if (const auto* System=NiagaraEffects.Find(SelectedElement); System && *System) {
        if (UNiagaraComponent* Niagara=UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(),System->Get(),Position)) {
            Niagara->SetVariableLinearColor(TEXT("User.Color"),ElementColor(SelectedElement));
            const TWeakObjectPtr<UNiagaraComponent> Weak(Niagara);
            FTimerHandle Timer;
            GetWorld()->GetTimerManager().SetTimer(Timer,FTimerDelegate::CreateLambda([Weak]() {
                if (Weak.IsValid()) Weak->DestroyComponent();
            }),3.f,false);
        }
    }
    return true;
}

ACryptoNyanAtmosphere::ACryptoNyanAtmosphere()
{
    PrimaryActorTick.bCanEverTick=true;
    auto* Root=CreateDefaultSubobject<USceneComponent>(TEXT("Root")); SetRootComponent(Root);
    Sun=CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("Sun")); Sun->SetupAttachment(Root);
    Sun->SetMobility(EComponentMobility::Movable);
    Sun->SetRelativeRotation(FRotator(-45,-30,0));
    Fog=CreateDefaultSubobject<UExponentialHeightFogComponent>(TEXT("Fog")); Fog->SetupAttachment(Root);
    Particles=CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Weather")); Particles->SetupAttachment(Root);
    Particles->SetCollisionEnabled(ECollisionEnabled::NoCollision); Particles->SetCanEverAffectNavigation(false);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (Cube.Succeeded()) Particles->SetStaticMesh(Cube.Object);
}
void ACryptoNyanAtmosphere::ConfigureAtmosphere(float Lux,float Density,ECryptoNyanWeather Weather)
{
    if (!FMath::IsFinite(Lux) || !FMath::IsFinite(Density) || uint8(Weather)>uint8(ECryptoNyanWeather::Ash)) return;
    Sun->SetIntensity(FMath::Clamp(Lux,0.f,120000.f));
    Fog->SetFogDensity(FMath::Clamp(Density,0.f,.1f));
    WeatherMode=Weather; Time=0;
    Particles->ClearInstances();
    if (WeatherMaterial) Particles->SetMaterial(0,WeatherMaterial);
    if (Weather!=ECryptoNyanWeather::Clear)
        for (int I=0; I<96; ++I) Particles->AddInstance(FTransform(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector));
}
void ACryptoNyanAtmosphere::Tick(float Delta)
{
    Super::Tick(Delta);
    if (!FMath::IsFinite(Delta) || Delta<0 || WeatherMode==ECryptoNyanWeather::Clear) return;
    Time+=Delta;
    const double Speed=WeatherMode==ECryptoNyanWeather::Rain ? 800 : 100;
    for (int I=0; I<96; ++I) {
        const double X=((I*173)%2000)-1000, Y=((I*311)%2000)-1000;
        const double Z=1200-FMath::Fmod(Time*Speed+I*37.,1200.);
        const FVector Scale(.02,.02,WeatherMode==ECryptoNyanWeather::Rain ? .2 : .02);
        Particles->UpdateInstanceTransform(I,FTransform(FQuat::Identity,FVector(X,Y,Z),Scale),false,I==95,true);
    }
}
