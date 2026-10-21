// SPDX-License-Identifier: MIT
#pragma once
#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "CryptoNyanCreative.h"
#include "CryptoNyanPowerMenu.generated.h"
class UTextBlock;
class UVerticalBox;

// Working C++ UMG demo menu; no generated widget blueprint or image dependency.
UCLASS(BlueprintType)
class CRYPTONYANRUNTIME_API UCryptoNyanPowerMenu : public UUserWidget
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="CryptoNyan") static UCryptoNyanPowerMenu* OpenPowerMenu(APlayerController* Player);
protected:
    virtual void NativeConstruct() override;
    virtual void NativeTick(const FGeometry& Geometry,float Delta) override;
private:
    UPROPERTY() TObjectPtr<UTextBlock> Status;
    UCryptoNyanPowerComponent* Power() const;
    void Select(ECryptoNyanElement Element);
    void Activate(ECryptoNyanPowerShape Shape);
    void AddButton(UVerticalBox* Box,const TCHAR* Label,FName Function);
    UFUNCTION() void Fire();
    UFUNCTION() void Ice();
    UFUNCTION() void Earth();
    UFUNCTION() void Wind();
    UFUNCTION() void Water();
    UFUNCTION() void Electric();
    UFUNCTION() void Dash();
    UFUNCTION() void Impact();
    UFUNCTION() void Projectile();
    UFUNCTION() void Zone();
    UFUNCTION() void Close();
};
