// SPDX-License-Identifier: MIT
#include "CryptoNyanSurfaceFeedback.h"
#include "Components/AudioComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Math/RotationMatrix.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundWave.h"
#include "TimerManager.h"

namespace {
bool Range(float V, float Low, float High) { return FMath::IsFinite(V) && V>=Low && V<=High; }
bool Pair(float Low, float High, float Minimum, float Maximum) {
    return Range(Low,Minimum,Maximum) && Range(High,Low,Maximum);
}
bool GroundHit(const FHitResult& Hit) {
    return Hit.bBlockingHit && !Hit.bStartPenetrating && !Hit.ImpactPoint.ContainsNaN() &&
        !Hit.ImpactNormal.ContainsNaN() && Hit.ImpactNormal.Z>=.2f;
}
}

bool UCryptoNyanSurfaceFeedbackProfile::ValidateProfile() const {
    if (!IsValid(TargetMesh) || FootSockets.Num()<1 || FootSockets.Num()>8 || Cues.Num()<1 || Cues.Num()>32 ||
        !Range(TraceUpCm,1,100) || !Range(TraceDownCm,1,200) || !Range(ContactCooldownSeconds,.04f,1) ||
        !Range(EventCooldownSeconds,.04f,1) || !Range(MinContactSpeedCmS,0,1000) ||
        !Range(HardStopSeconds,.05f,5) || MaxActiveSounds<1 || MaxActiveSounds>16 ||
        MaxActiveEffects<1 || MaxActiveEffects>16) return false;
    TSet<FName> Feet;
    for (FName Foot: FootSockets) { if (Foot.IsNone() || Feet.Contains(Foot)) return false; Feet.Add(Foot); }
    for (int32 I=0; I<Cues.Num(); ++I) {
        const auto& Cue=Cues[I];
        if (uint8(Cue.Kind)>2 || Cue.Sounds.Num()>8 || (Cue.Sounds.IsEmpty() && !IsValid(Cue.Niagara)) ||
            (!Cue.Sounds.IsEmpty() && !IsValid(Attenuation)) || !Pair(Cue.MinVolume,Cue.MaxVolume,0,1) ||
            !Pair(Cue.MinPitch,Cue.MaxPitch,.5f,2) || !Pair(Cue.MinEffectScale,Cue.MaxEffectScale,.01f,3) ||
            !Range(Cue.ReferenceSpeedCmS,1,5000)) return false;
        for (int32 J=0; J<I; ++J)
            if (Cues[J].Kind==Cue.Kind && Cues[J].PhysicalMaterial==Cue.PhysicalMaterial) return false;
        TSet<USoundWave*> Seen;
        for (auto Sound: Cue.Sounds) {
            if (!IsValid(Sound) || Seen.Contains(Sound) || Sound->bLooping || Sound->NumChannels!=1 ||
                !Range(Sound->GetDuration(),.001f,HardStopSeconds*Cue.MinPitch)) return false;
            Seen.Add(Sound);
        }
    }
    return true;
}

UCryptoNyanSurfaceFeedbackComponent::UCryptoNyanSurfaceFeedbackComponent() {
    PrimaryComponentTick.bCanEverTick=false;
    bAutoActivate=true;
}
void UCryptoNyanSurfaceFeedbackComponent::BeginPlay() {
    Super::BeginPlay(); Character=Cast<ACharacter>(GetOwner()); Random.Initialize(VariationSeed);
    Gate=CryptoNyanFeedbackRules::Gate(); PreviousVariants.Reset(); EmittedEvents=RejectedEvents=0;
    if (Character.IsValid()) Character->LandedDelegate.AddUniqueDynamic(this,&UCryptoNyanSurfaceFeedbackComponent::Landed);
}
void UCryptoNyanSurfaceFeedbackComponent::EndPlay(const EEndPlayReason::Type Reason) {
    if (Character.IsValid()) Character->LandedDelegate.RemoveDynamic(this,&UCryptoNyanSurfaceFeedbackComponent::Landed);
    for (auto Item: Audio) if (Item.IsValid()) { Item->Stop(); Item->DestroyComponent(); }
    for (auto Item: Effects) if (Item.IsValid()) Item->DestroyComponent();
    Audio.Reset(); Effects.Reset(); Character.Reset(); Super::EndPlay(Reason);
}
bool UCryptoNyanSurfaceFeedbackComponent::Ready() const {
    const auto* World=GetWorld(); const auto* Owner=Character.Get();
    if (!Owner) return false;
    TArray<UCryptoNyanSurfaceFeedbackComponent*> Components;
    Owner->GetComponents<UCryptoNyanSurfaceFeedbackComponent>(Components);
    return Components.Num()==1 && Components[0]==this && IsActive() && World && World->IsGameWorld() && World->GetNetMode()==NM_Standalone &&
        Owner->HasActorBegunPlay() && Owner->GetMesh() && Owner->GetCapsuleComponent() && Owner->GetCharacterMovement() &&
        IsValid(Profile) && Profile->ValidateProfile() &&
        Owner->GetMesh()->GetSkeletalMeshAsset()==Profile->TargetMesh;
}
bool UCryptoNyanSurfaceFeedbackComponent::Trace(const FVector& Origin, FHitResult& Hit) const {
    if (Origin.ContainsNaN()) return false;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(CryptoNyanSurfaceFeedback),false,GetOwner());
    Params.bReturnPhysicalMaterial=true;
    return GetWorld()->LineTraceSingleByChannel(Hit,Origin+FVector(0,0,Profile->TraceUpCm),
        Origin-FVector(0,0,Profile->TraceDownCm),ECC_Visibility,Params) && GroundHit(Hit);
}
bool UCryptoNyanSurfaceFeedbackComponent::Contact(USkeletalMeshComponent* Mesh, FName Foot) {
    if (!Ready() || Mesh!=Character->GetMesh() || !Mesh->DoesSocketExist(Foot) ||
        !Character->GetCharacterMovement()->IsMovingOnGround()) { ++RejectedEvents; return false; }
    const int32 Channel=Profile->FootSockets.IndexOfByKey(Foot);
    const float Speed=Character->GetVelocity().Size2D(); FHitResult Hit;
    if (Channel==INDEX_NONE || !FMath::IsFinite(Speed) || Speed<Profile->MinContactSpeedCmS ||
        !Trace(Mesh->GetSocketLocation(Foot),Hit)) { ++RejectedEvents; return false; }
    return Emit(ECryptoNyanFeedbackKind::Contact,Channel,Foot,Hit,Speed);
}
bool UCryptoNyanSurfaceFeedbackComponent::NotifyJump() {
    if (!Ready()) { ++RejectedEvents; return false; }
    FHitResult Hit; const auto* Owner=Character.Get();
    const FVector Feet=Owner->GetActorLocation()-FVector(0,0,Owner->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    if (!Trace(Feet,Hit)) { ++RejectedEvents; return false; }
    return Emit(ECryptoNyanFeedbackKind::Jump,8,NAME_None,Hit,Owner->GetVelocity().Size());
}
void UCryptoNyanSurfaceFeedbackComponent::Landed(const FHitResult& Hit) {
    if (!Ready() || !GroundHit(Hit)) { ++RejectedEvents; return; }
    // ACharacter::Landed runs before falling velocity is cleared. Query again for
    // the physical material because movement sweeps need not return one.
    FHitResult Surface;
    if (!Trace(Hit.ImpactPoint,Surface)) { ++RejectedEvents; return; }
    const FVector Velocity=Character->GetVelocity();
    if (Velocity.ContainsNaN()) { ++RejectedEvents; return; }
    Emit(ECryptoNyanFeedbackKind::Landing,9,NAME_None,Surface,float(FMath::Max(0.,-Velocity.Z)));
}
bool UCryptoNyanSurfaceFeedbackComponent::Emit(ECryptoNyanFeedbackKind Kind, int32 Channel, FName Socket,
    const FHitResult& Hit, float Speed) {
    std::array<CryptoNyanFeedbackRules::CueKey,32> Keys;
    for (int32 I=0; I<Profile->Cues.Num(); ++I) {
        const auto& Cue=Profile->Cues[I];
        Keys[I]={int(Cue.Kind),reinterpret_cast<std::uintptr_t>(Cue.PhysicalMaterial.Get())};
    }
    const int32 Selected=CryptoNyanFeedbackRules::Select(Keys.data(),Profile->Cues.Num(),int(Kind),
        reinterpret_cast<std::uintptr_t>(Hit.PhysMaterial.Get()));
    const double Cooldown=Kind==ECryptoNyanFeedbackKind::Contact ? Profile->ContactCooldownSeconds : Profile->EventCooldownSeconds;
    if (Selected==INDEX_NONE || !FMath::IsFinite(Speed) || Speed<0 ||
        !Gate.Admit(Channel,GetWorld()->GetTimeSeconds(),Cooldown)) { ++RejectedEvents; return false; }
    const auto& Cue=Profile->Cues[Selected];
    const float Strength=float(CryptoNyanFeedbackRules::Intensity(Speed,Cue.ReferenceSpeedCmS));
    Audio.RemoveAll([](const auto& P) { return !P.IsValid() || !P->IsPlaying(); });
    Effects.RemoveAll([](const auto& P) { return !P.IsValid() || P->IsComplete(); });
    bool Emitted=false;
    if (!Cue.Sounds.IsEmpty() && Audio.Num()<Profile->MaxActiveSounds) {
        const int32* Previous=PreviousVariants.Find(Selected);
        const int32 Pick=CryptoNyanFeedbackRules::Variant(Cue.Sounds.Num(),Previous ? *Previous : -1,Random.GetUnsignedInt());
        auto* Sound=UGameplayStatics::SpawnSoundAtLocation(this,Cue.Sounds[Pick],Hit.ImpactPoint,FRotator::ZeroRotator,
            FMath::Lerp(Cue.MinVolume,Cue.MaxVolume,Strength),Random.FRandRange(Cue.MinPitch,Cue.MaxPitch),0,
            Profile->Attenuation,nullptr,true);
        if (Sound) {
            PreviousVariants.Add(Selected,Pick); Audio.Add(Sound); Emitted=true;
            const TWeakObjectPtr<UAudioComponent> Weak(Sound); FTimerHandle Timer;
            GetWorld()->GetTimerManager().SetTimer(Timer,FTimerDelegate::CreateLambda([Weak]() {
                if (Weak.IsValid()) { Weak->Stop(); Weak->DestroyComponent(); }
            }),Profile->HardStopSeconds,false);
        }
    }
    if (Cue.Niagara && Effects.Num()<Profile->MaxActiveEffects) {
        const float Scale=FMath::Lerp(Cue.MinEffectScale,Cue.MaxEffectScale,Strength);
        auto* Effect=UNiagaraFunctionLibrary::SpawnSystemAtLocation(this,Cue.Niagara,Hit.ImpactPoint,
            FRotationMatrix::MakeFromZ(Hit.ImpactNormal).Rotator(),FVector(Scale),true,true);
        if (Effect) {
            Effects.Add(Effect); Emitted=true;
            const TWeakObjectPtr<UNiagaraComponent> Weak(Effect); FTimerHandle Timer;
            GetWorld()->GetTimerManager().SetTimer(Timer,FTimerDelegate::CreateLambda([Weak]() {
                if (Weak.IsValid()) Weak->DestroyComponent();
            }),Profile->HardStopSeconds,false);
        }
    }
    if (Emitted) { ++EmittedEvents; OnFeedbackEmitted.Broadcast(Kind,Socket,Hit.PhysMaterial.Get(),Hit.ImpactPoint,Strength); }
    else ++RejectedEvents;
    return Emitted;
}

UCryptoNyanContactNotify::UCryptoNyanContactNotify() {
#if WITH_EDITORONLY_DATA
    bShouldFireInEditor=false;
#endif
}
void UCryptoNyanContactNotify::Notify(USkeletalMeshComponent* Mesh, UAnimSequenceBase* Animation,
    const FAnimNotifyEventReference& Reference) {
    (void)Animation; (void)Reference;
    if (Mesh && Mesh->GetOwner())
        if (auto* Feedback=Mesh->GetOwner()->FindComponentByClass<UCryptoNyanSurfaceFeedbackComponent>())
            Feedback->Contact(Mesh,FootSocket);
}
