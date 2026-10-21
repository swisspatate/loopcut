// SPDX-License-Identifier: MIT
#include "CryptoNyanPowerMenu.h"
#include "Blueprint/WidgetTree.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/VerticalBox.h"
#include "Components/TextBlock.h"
#include "Components/Button.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Pawn.h"

UCryptoNyanPowerMenu* UCryptoNyanPowerMenu::OpenPowerMenu(APlayerController* Player)
{
    if (!Player || !Player->IsLocalController()) return nullptr;
    auto* Menu=CreateWidget<UCryptoNyanPowerMenu>(Player,StaticClass());
    if (!Menu) return nullptr;
    Menu->AddToViewport();
    Player->bShowMouseCursor=true;
    FInputModeGameAndUI Mode;
    Mode.SetWidgetToFocus(Menu->TakeWidget());
    Player->SetInputMode(Mode);
    return Menu;
}
UCryptoNyanPowerComponent* UCryptoNyanPowerMenu::Power() const
{
    return GetOwningPlayerPawn() ? GetOwningPlayerPawn()->FindComponentByClass<UCryptoNyanPowerComponent>() : nullptr;
}
void UCryptoNyanPowerMenu::NativeConstruct()
{
    Super::NativeConstruct();
    if (!WidgetTree) WidgetTree=NewObject<UWidgetTree>(this);
    if (WidgetTree->RootWidget) return;
    auto* Canvas=WidgetTree->ConstructWidget<UCanvasPanel>();
    WidgetTree->RootWidget=Canvas;
    auto* Box=WidgetTree->ConstructWidget<UVerticalBox>();
    auto* Slot=Canvas->AddChildToCanvas(Box);
    Slot->SetPosition(FVector2D(24,24)); Slot->SetSize(FVector2D(360,650));
    Status=WidgetTree->ConstructWidget<UTextBlock>(); Box->AddChildToVerticalBox(Status);
    AddButton(Box,TEXT("Feu"),TEXT("Fire")); AddButton(Box,TEXT("Glace"),TEXT("Ice"));
    AddButton(Box,TEXT("Terre"),TEXT("Earth")); AddButton(Box,TEXT("Vent"),TEXT("Wind"));
    AddButton(Box,TEXT("Eau"),TEXT("Water")); AddButton(Box,TEXT("Electricite"),TEXT("Electric"));
    AddButton(Box,TEXT("Dash"),TEXT("Dash")); AddButton(Box,TEXT("Impact"),TEXT("Impact"));
    AddButton(Box,TEXT("Projectile"),TEXT("Projectile")); AddButton(Box,TEXT("Zone"),TEXT("Zone"));
    AddButton(Box,TEXT("Fermer"),TEXT("Close"));
}
void UCryptoNyanPowerMenu::AddButton(UVerticalBox* Box,const TCHAR* Label,FName Function)
{
    auto* Button=WidgetTree->ConstructWidget<UButton>();
    auto* Text=WidgetTree->ConstructWidget<UTextBlock>(); Text->SetText(FText::FromString(Label));
    Button->AddChild(Text); Box->AddChildToVerticalBox(Button);
    FScriptDelegate Callback; Callback.BindUFunction(this,Function); Button->OnClicked.Add(Callback);
}
void UCryptoNyanPowerMenu::NativeTick(const FGeometry& Geometry,float Delta)
{
    Super::NativeTick(Geometry,Delta);
    if (!Status) return;
    const auto* Component=Power();
    Status->SetText(Component ? FText::FromString(FString::Printf(TEXT("CryptoNyan | %s | Energie %.0f"),
        *UEnum::GetValueAsString(Component->SelectedElement),Component->Energy)) :
        FText::FromString(TEXT("Ajouter CryptoNyanPowerComponent au personnage")));
}
void UCryptoNyanPowerMenu::Select(ECryptoNyanElement E) { if (auto* C=Power()) C->SelectedElement=E; }
void UCryptoNyanPowerMenu::Activate(ECryptoNyanPowerShape S) { if (auto* C=Power()) C->ActivatePower(S,GetOwningPlayerPawn()->GetActorForwardVector()); }
void UCryptoNyanPowerMenu::Fire() { Select(ECryptoNyanElement::Fire); }
void UCryptoNyanPowerMenu::Ice() { Select(ECryptoNyanElement::Ice); }
void UCryptoNyanPowerMenu::Earth() { Select(ECryptoNyanElement::Earth); }
void UCryptoNyanPowerMenu::Wind() { Select(ECryptoNyanElement::Wind); }
void UCryptoNyanPowerMenu::Water() { Select(ECryptoNyanElement::Water); }
void UCryptoNyanPowerMenu::Electric() { Select(ECryptoNyanElement::Electric); }
void UCryptoNyanPowerMenu::Dash() { Activate(ECryptoNyanPowerShape::Dash); }
void UCryptoNyanPowerMenu::Impact() { Activate(ECryptoNyanPowerShape::Impact); }
void UCryptoNyanPowerMenu::Projectile() { Activate(ECryptoNyanPowerShape::Projectile); }
void UCryptoNyanPowerMenu::Zone() { Activate(ECryptoNyanPowerShape::Zone); }
void UCryptoNyanPowerMenu::Close()
{
    if (auto* Player=GetOwningPlayer()) { Player->bShowMouseCursor=false; Player->SetInputMode(FInputModeGameOnly()); }
    RemoveFromParent();
}
