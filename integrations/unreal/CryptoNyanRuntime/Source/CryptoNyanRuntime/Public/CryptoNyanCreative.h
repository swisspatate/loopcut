// SPDX-License-Identifier: MIT
#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Components/ActorComponent.h"
#include "CryptoNyanElements.h"
#include "CryptoNyanCreative.generated.h"

class UBoxComponent;
class USphereComponent;
class UStaticMeshComponent;
class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UNiagaraSystem;
class UDirectionalLightComponent;
class UExponentialHeightFogComponent;

UENUM(BlueprintType)
enum class ECryptoNyanElement : uint8 { Fire, Ice, Earth, Wind, Water, Electric };
UENUM(BlueprintType)
enum class ECryptoNyanPowerShape : uint8 { Dash, Impact, Projectile, Zone };
UENUM(BlueprintType)
enum class ECryptoNyanWeather : uint8 { Clear, Rain, Snow, Ash };

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FCryptoNyanElementChanged, ECryptoNyanElement, Element);

UCLASS(BlueprintType)
class CRYPTONYANRUNTIME_API ACryptoNyanElementSurface : public AActor
{
    GENERATED_BODY()
public:
    ACryptoNyanElementSurface();
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") bool Flammable=false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") bool Freezable=true;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") bool Conductive=false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") bool Movable=false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") bool Liquid=false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") bool InitiallyWet=false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan", meta=(ClampMin="0", ClampMax="500")) float RiseCm=200;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") bool Wet=false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") bool Frozen=false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") bool Burned=false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") bool Charged=false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") bool Raised=false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") TObjectPtr<UStaticMeshComponent> Surface;
    UPROPERTY(BlueprintAssignable, Category="CryptoNyan") FCryptoNyanElementChanged OnElementChanged;
    UFUNCTION(BlueprintCallable, Category="CryptoNyan") bool ApplyElement(ECryptoNyanElement Element, FVector Direction);
    UFUNCTION(BlueprintCallable, Category="CryptoNyan") void ResetElements();
protected:
    virtual void BeginPlay() override;
private:
    UPROPERTY() TObjectPtr<UBoxComponent> Collision;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> DynamicMaterial;
    FVector Origin=FVector::ZeroVector;
    CryptoNyanElements::State State;
    void ApplyState();
};

UCLASS(BlueprintType)
class CRYPTONYANRUNTIME_API ACryptoNyanElementEffect : public AActor
{
    GENERATED_BODY()
public:
    ACryptoNyanElementEffect();
    void Start(ECryptoNyanElement InElement, ECryptoNyanPowerShape InShape, FVector Direction, float Radius,
               UMaterialInterface* Material);
    virtual void Tick(float DeltaSeconds) override;
private:
    UPROPERTY() TObjectPtr<USphereComponent> Collision;
    UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Particles;
    ECryptoNyanElement Element=ECryptoNyanElement::Fire;
    ECryptoNyanPowerShape Shape=ECryptoNyanPowerShape::Impact;
    FVector Velocity=FVector::ZeroVector;
    float Age=0, Duration=.6f, ZoneRadius=300, NextPulse=0;
    TSet<TWeakObjectPtr<AActor>> Affected;
    void AffectNearby();
};

UCLASS(ClassGroup=(CryptoNyan), meta=(BlueprintSpawnableComponent))
class CRYPTONYANRUNTIME_API UCryptoNyanPowerComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UCryptoNyanPowerComponent();
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") ECryptoNyanElement SelectedElement=ECryptoNyanElement::Fire;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") float Energy=100;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan", meta=(ClampMin="1", ClampMax="100")) float Cost=10;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan", meta=(ClampMin="0.05", ClampMax="60")) float Cooldown=.5f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan", meta=(ClampMin="25", ClampMax="1000")) float RadiusCm=250;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan", meta=(ClampMin="100", ClampMax="2000")) float DashSpeed=800;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TObjectPtr<UMaterialInterface> EffectMaterial;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TMap<ECryptoNyanElement, TObjectPtr<UNiagaraSystem>> NiagaraEffects;
    UFUNCTION(BlueprintCallable, Category="CryptoNyan") bool ActivatePower(ECryptoNyanPowerShape Shape, FVector Direction);
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
private:
    double ReadyAt=0;
};

UCLASS(BlueprintType)
class CRYPTONYANRUNTIME_API ACryptoNyanAtmosphere : public AActor
{
    GENERATED_BODY()
public:
    ACryptoNyanAtmosphere();
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") TObjectPtr<UDirectionalLightComponent> Sun;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="CryptoNyan") TObjectPtr<UExponentialHeightFogComponent> Fog;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="CryptoNyan") TObjectPtr<UMaterialInterface> WeatherMaterial;
    UFUNCTION(BlueprintCallable, Category="CryptoNyan") void ConfigureAtmosphere(float SunLux, float FogDensity, ECryptoNyanWeather Weather);
    virtual void Tick(float DeltaSeconds) override;
private:
    UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Particles;
    UPROPERTY() ECryptoNyanWeather WeatherMode=ECryptoNyanWeather::Clear;
    double Time=0;
};
