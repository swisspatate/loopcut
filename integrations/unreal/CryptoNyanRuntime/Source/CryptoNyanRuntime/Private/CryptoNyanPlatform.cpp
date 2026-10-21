// SPDX-License-Identifier: MIT
#include "CryptoNyanPlatform.h"
#include "CryptoNyanMotion.h"
#include "Components/SceneComponent.h"
#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInterface.h"

ACryptoNyanPlatform::ACryptoNyanPlatform()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickGroup = TG_PrePhysics;
    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    SetRootComponent(SceneRoot);
    SceneRoot->SetMobility(EComponentMobility::Movable);
    Surface = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Surface"));
    Surface->SetupAttachment(SceneRoot);
    Surface->SetMobility(EComponentMobility::Movable);
    Surface->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Surface->SetCanEverAffectNavigation(false);
    FloorCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("FloorCollision"));
    FloorCollision->SetupAttachment(SceneRoot);
    FloorCollision->SetMobility(EComponentMobility::Movable);
    FloorCollision->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    FloorCollision->SetCollisionObjectType(ECC_WorldDynamic);
    FloorCollision->SetCollisionResponseToAllChannels(ECR_Ignore);
    FloorCollision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
    FloorCollision->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
    FloorCollision->CanCharacterStepUpOn = ECB_Yes;
    FloorCollision->SetGenerateOverlapEvents(false);
    FloorCollision->SetCanEverAffectNavigation(false);
}

bool ACryptoNyanPlatform::ConfigurePlatform(UStaticMesh* Mesh, UMaterialInterface* Material,
    FVector RestLocation, bool CollisionEnabled, double AmplitudeCm, double PeriodSeconds, double PhaseSeconds)
{
    if (!Mesh || !Material || RestLocation.ContainsNaN() || !FMath::IsFinite(AmplitudeCm) ||
        !FMath::IsFinite(PeriodSeconds) || !FMath::IsFinite(PhaseSeconds) ||
        AmplitudeCm < 0.0 || AmplitudeCm > 300.0 || PeriodSeconds <= 0.0 || PeriodSeconds > 20.0 ||
        PhaseSeconds < 0.0 || PhaseSeconds >= PeriodSeconds)
        return false;
    const FBox Bounds = Mesh->GetBoundingBox();
    const FVector Extent = Bounds.GetExtent();
    if (!Bounds.IsValid || Extent.ContainsNaN() || Extent.GetMin() <= 0.0)
        return false;
    Surface->SetStaticMesh(Mesh);
    Surface->SetMaterial(0, Material);
    FloorCollision->SetBoxExtent(Extent, false);
    FloorCollision->SetRelativeLocation(Bounds.GetCenter());
    FloorCollision->SetCollisionEnabled(CollisionEnabled ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
    Origin = RestLocation;
    Amplitude = AmplitudeCm;
    Period = PeriodSeconds;
    Phase = PhaseSeconds;
    bConfigured = true;
    ResetMotion();
    return true;
}

void ACryptoNyanPlatform::ApplyTime(double Seconds)
{
    if (bConfigured)
        SetActorLocation(Origin + FVector(0.0, 0.0, Amplitude * CryptoNyanMotion::Triangle(Seconds, Period, Phase)),
                         false, nullptr, ETeleportType::None);
}

void ACryptoNyanPlatform::ResetMotion()
{
    Epoch = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
    ApplyTime(0.0);
    SetActorTickEnabled(bConfigured && Amplitude > 0.0);
}

void ACryptoNyanPlatform::BeginPlay()
{
    Super::BeginPlay();
    ResetMotion();
}

double ACryptoNyanPlatform::GetMotionElapsedSeconds() const
{
    return GetWorld() ? GetWorld()->GetTimeSeconds() - Epoch : 0.0;
}

void ACryptoNyanPlatform::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    ApplyTime(0.0);
}

void ACryptoNyanPlatform::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (GetWorld()) ApplyTime(GetMotionElapsedSeconds());
}
