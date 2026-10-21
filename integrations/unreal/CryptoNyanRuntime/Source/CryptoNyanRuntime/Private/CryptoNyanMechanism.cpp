// SPDX-License-Identifier: MIT
#include "CryptoNyanMechanism.h"
#include "CryptoNyanMechanismRules.h"
#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/World.h"

namespace { const FName Claim(TEXT("CryptoNyanMovementOverride")); }
ACryptoNyanMechanism::ACryptoNyanMechanism() {
    PrimaryActorTick.bCanEverTick=true;
    Trigger=CreateDefaultSubobject<UBoxComponent>(TEXT("MechanismTrigger"));
    Trigger->SetupAttachment(GetRootComponent());
    Trigger->SetCollisionProfileName(TEXT("Trigger"));
    Trigger->SetGenerateOverlapEvents(true);
}
bool ACryptoNyanMechanism::ConfigureMechanism(int32 Kind,int32 Element,float Strength,FVector Extent) {
    if (HasActorBegunPlay() || !CryptoNyanMechanismRules::Valid(Kind,Element,Strength) || Extent.ContainsNaN() ||
        Extent.GetMin()<10 || Extent.GetMax()>5000) return false;
    MechanismKind=Kind; RequiredElement=Element; Power=Strength;
    Trigger->SetBoxExtent(Extent);
    if (auto* Box=Cast<UBoxComponent>(GetRootComponent())) Box->SetBoxExtent(Extent);
    Surface->SetRelativeScale3D(Extent/50.f);
    ApplyCollision();
    return true;
}
void ACryptoNyanMechanism::ApplyCollision() {
    const bool Solid=MechanismKind<2 && !Activated;
    if (auto* Box=Cast<UBoxComponent>(GetRootComponent()))
        Box->SetCollisionEnabled(Solid ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
    Surface->SetVisibility(Solid);
    Trigger->SetCollisionEnabled(MechanismKind>=2 ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
}
void ACryptoNyanMechanism::BeginPlay() { Super::BeginPlay(); Activated=false; ApplyCollision(); }
void ACryptoNyanMechanism::ResetElements() {
    for (const auto& Pair: Visitors) Release(Pair.Key.Get(),Pair.Value);
    Visitors.Empty(); Activated=false;
    Super::ResetElements(); ApplyCollision();
}
bool ACryptoNyanMechanism::ApplyElement(ECryptoNyanElement Element,FVector Direction) {
    if (!GetWorld() || GetNetMode()!=NM_Standalone || !CryptoNyanMechanismRules::Activate(MechanismKind,RequiredElement,int(Element),Activated)) return false;
    Activated=true; ApplyCollision(); OnActivated.Broadcast(nullptr); return true;
}
void ACryptoNyanMechanism::Release(ACharacter* Character,const FPrevious& Previous) {
    if (!IsValid(Character)) return;
    auto* Move=Character->GetCharacterMovement();
    if (!Move) { Character->Tags.Remove(Claim); return; }
    if (MechanismKind==3 && FMath::IsNearlyEqual(Move->GravityScale,float(CryptoNyanMechanismRules::Gravity(Power)))) Move->GravityScale=Previous.Gravity;
    if (MechanismKind==4) {
        if (FMath::IsNearlyEqual(Move->GroundFriction,.1f)) Move->GroundFriction=Previous.Friction;
        if (FMath::IsNearlyEqual(Move->BrakingFrictionFactor,.1f)) Move->BrakingFrictionFactor=Previous.Braking;
    }
    Character->Tags.Remove(Claim);
}
void ACryptoNyanMechanism::Tick(float Delta) {
    Super::Tick(Delta);
    if (!GetWorld() || GetNetMode()!=NM_Standalone || !FMath::IsFinite(Delta) || Delta<=0 || MechanismKind<2) return;
    TArray<AActor*> Overlaps; Trigger->GetOverlappingActors(Overlaps,ACharacter::StaticClass());
    TSet<TWeakObjectPtr<ACharacter>> Present;
    for (AActor* Actor : Overlaps) {
        auto* Character=Cast<ACharacter>(Actor);
        if (!Character || Present.Num()>=32) continue;
        Present.Add(Character);
        auto* Move=Character->GetCharacterMovement();
        if (!Move) continue;
        if (MechanismKind==2) {
            Move->AddImpulse(GetActorUpVector()*CryptoNyanMechanismRules::WindImpulse(Power,Delta),true);
        } else if (MechanismKind==5) {
            if (!Activated) { Activated=true; OnActivated.Broadcast(Character); }
        } else if (!Visitors.Contains(Character) && !Character->Tags.Contains(Claim)) {
            Visitors.Add(Character,FPrevious{Move->GravityScale,Move->GroundFriction,Move->BrakingFrictionFactor});
            Character->Tags.AddUnique(Claim);
            if (MechanismKind==3) Move->GravityScale=CryptoNyanMechanismRules::Gravity(Power);
            else { Move->GroundFriction=.1f; Move->BrakingFrictionFactor=.1f; }
        }
    }
    for (auto It=Visitors.CreateIterator(); It; ++It) {
        if (!Present.Contains(It.Key())) { Release(It.Key().Get(),It.Value()); It.RemoveCurrent(); }
    }
}
void ACryptoNyanMechanism::EndPlay(const EEndPlayReason::Type Reason) {
    for (const auto& Pair: Visitors) Release(Pair.Key.Get(),Pair.Value);
    Visitors.Empty(); Super::EndPlay(Reason);
}
