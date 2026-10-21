// SPDX-License-Identifier: MIT
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CryptoNyanPlatform.generated.h"

class UBoxComponent;
class USceneComponent;
class UStaticMeshComponent;
class UStaticMesh;
class UMaterialInterface;

UCLASS(BlueprintType)
class CRYPTONYANRUNTIME_API ACryptoNyanPlatform : public AActor
{
    GENERATED_BODY()
public:
    ACryptoNyanPlatform();
    virtual void Tick(float DeltaSeconds) override;
    virtual void OnConstruction(const FTransform& Transform) override;

    // Configure only a cuboid module: collision is its local bounding box.
    UFUNCTION(BlueprintCallable, Category="CryptoNyan")
    bool ConfigurePlatform(UStaticMesh* Mesh, UMaterialInterface* Material, FVector RestLocation,
                           bool CollisionEnabled, double AmplitudeCm, double PeriodSeconds, double PhaseSeconds);

    UFUNCTION(BlueprintCallable, Category="CryptoNyan")
    void ResetMotion();

    UFUNCTION(BlueprintPure, Category="CryptoNyan")
    double GetMotionElapsedSeconds() const;

protected:
    virtual void BeginPlay() override;
private:
    void ApplyTime(double Seconds);
    UPROPERTY(VisibleAnywhere, Category="CryptoNyan") TObjectPtr<USceneComponent> SceneRoot;
    UPROPERTY(VisibleAnywhere, Category="CryptoNyan") TObjectPtr<UStaticMeshComponent> Surface;
    UPROPERTY(VisibleAnywhere, Category="CryptoNyan") TObjectPtr<UBoxComponent> FloorCollision;
    UPROPERTY() FVector Origin = FVector::ZeroVector;
    UPROPERTY() double Amplitude = 0.0;
    UPROPERTY() double Period = 1.0;
    UPROPERTY() double Phase = 0.0;
    UPROPERTY() bool bConfigured = false;
    double Epoch = 0.0;
};
