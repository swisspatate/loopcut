// SPDX-License-Identifier: MIT
#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "Components/ActorComponent.h"
#include "Engine/DataAsset.h"
#include "CryptoNyanFeedbackRules.h"
#include "CryptoNyanSurfaceFeedback.generated.h"

class ACharacter;
class USkeletalMesh;
class USkeletalMeshComponent;
class UPhysicalMaterial;
class USoundWave;
class USoundAttenuation;
class UAudioComponent;
class UNiagaraSystem;
class UNiagaraComponent;

UENUM(BlueprintType)
enum class ECryptoNyanFeedbackKind : uint8 { Contact, Jump, Landing };

USTRUCT(BlueprintType)
struct CRYPTONYANRUNTIME_API FCryptoNyanSurfaceFeedbackCue {
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") ECryptoNyanFeedbackKind Kind=ECryptoNyanFeedbackKind::Contact;
    // Null is an explicit fallback for a real hit, never permission to emit in air.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TObjectPtr<UPhysicalMaterial> PhysicalMaterial;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TArray<TObjectPtr<USoundWave>> Sounds;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TObjectPtr<UNiagaraSystem> Niagara;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float MinVolume=.2f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float MaxVolume=1;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float MinPitch=.95f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float MaxPitch=1.05f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float MinEffectScale=.5f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float MaxEffectScale=1;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float ReferenceSpeedCmS=600;
};

UCLASS(BlueprintType)
class CRYPTONYANRUNTIME_API UCryptoNyanSurfaceFeedbackProfile : public UDataAsset {
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TObjectPtr<USkeletalMesh> TargetMesh;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TArray<FName> FootSockets;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TArray<FCryptoNyanSurfaceFeedbackCue> Cues;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TObjectPtr<USoundAttenuation> Attenuation;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float TraceUpCm=15;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float TraceDownCm=45;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float ContactCooldownSeconds=.08f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float EventCooldownSeconds=.2f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float MinContactSpeedCmS=5;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") float HardStopSeconds=3;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") int32 MaxActiveSounds=8;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") int32 MaxActiveEffects=8;
    UFUNCTION(BlueprintPure, Category="CryptoNyan") bool ValidateProfile() const;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_FiveParams(FCryptoNyanFeedbackEmitted, ECryptoNyanFeedbackKind, Kind,
    FName, FootSocket, UPhysicalMaterial*, Surface, FVector, Location, float, Intensity);

UCLASS(ClassGroup=(CryptoNyan), meta=(BlueprintSpawnableComponent))
class CRYPTONYANRUNTIME_API UCryptoNyanSurfaceFeedbackComponent : public UActorComponent {
    GENERATED_BODY()
public:
    UCryptoNyanSurfaceFeedbackComponent();
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TObjectPtr<UCryptoNyanSurfaceFeedbackProfile> Profile;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") int32 VariationSeed=42;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") int32 EmittedEvents=0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") int32 RejectedEvents=0;
    UPROPERTY(BlueprintAssignable, Category="CryptoNyan") FCryptoNyanFeedbackEmitted OnFeedbackEmitted;
    UFUNCTION(BlueprintCallable, Category="CryptoNyan") bool Contact(USkeletalMeshComponent* Mesh, FName FootSocket);
    // Wire from the existing Character's OnJumped event. Walking off a ledge is not a jump.
    UFUNCTION(BlueprintCallable, Category="CryptoNyan") bool NotifyJump();
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
private:
    TWeakObjectPtr<ACharacter> Character;
    CryptoNyanFeedbackRules::Gate Gate;
    FRandomStream Random;
    TMap<int32,int32> PreviousVariants;
    TArray<TWeakObjectPtr<UAudioComponent>> Audio;
    TArray<TWeakObjectPtr<UNiagaraComponent>> Effects;
    UFUNCTION() void Landed(const FHitResult& Hit);
    bool Ready() const;
    bool Trace(const FVector& Origin, FHitResult& Hit) const;
    bool Emit(ECryptoNyanFeedbackKind Kind, int32 Channel, FName Socket, const FHitResult& Hit, float Speed);
};

// Notify objects are shared between actors: all mutable state lives on the component.
UCLASS(meta=(DisplayName="CryptoNyan Surface Contact"))
class CRYPTONYANRUNTIME_API UCryptoNyanContactNotify : public UAnimNotify {
    GENERATED_BODY()
public:
    UCryptoNyanContactNotify();
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") FName FootSocket;
    virtual void Notify(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation,
                        const FAnimNotifyEventReference& EventReference) override;
};
