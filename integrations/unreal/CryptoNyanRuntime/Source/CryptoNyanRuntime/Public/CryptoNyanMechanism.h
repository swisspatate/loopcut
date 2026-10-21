// SPDX-License-Identifier: MIT
#pragma once
#include "CoreMinimal.h"
#include "CryptoNyanCreative.h"
#include "CryptoNyanMechanism.generated.h"
class ACharacter;
class UBoxComponent;
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FCryptoNyanMechanismActivated, AActor*, Visitor);

// Standalone review mechanisms. Kind: gate, breakable, wind, gravity, ice, beacon.
UCLASS(BlueprintType)
class CRYPTONYANRUNTIME_API ACryptoNyanMechanism : public ACryptoNyanElementSurface {
    GENERATED_BODY()
public:
    ACryptoNyanMechanism();
    UFUNCTION(BlueprintCallable, Category="CryptoNyan") bool ConfigureMechanism(int32 Kind, int32 Element, float Strength, FVector HalfExtentCm);
    virtual bool ApplyElement(ECryptoNyanElement Element, FVector Direction) override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void ResetElements() override;
    UPROPERTY(BlueprintAssignable, Category="CryptoNyan") FCryptoNyanMechanismActivated OnActivated;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") bool Activated=false;
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    UPROPERTY() TObjectPtr<UBoxComponent> Trigger;
    UPROPERTY() int32 MechanismKind=5;
    UPROPERTY() int32 RequiredElement=0;
    UPROPERTY() float Power=1;
    struct FPrevious { float Gravity=1, Friction=8, Braking=2; };
    TMap<TWeakObjectPtr<ACharacter>, FPrevious> Visitors;
    void Release(ACharacter* Character, const FPrevious& Previous);
    void ApplyCollision();
};
