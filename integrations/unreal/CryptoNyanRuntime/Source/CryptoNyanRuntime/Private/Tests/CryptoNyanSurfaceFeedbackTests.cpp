// SPDX-License-Identifier: MIT
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "CryptoNyanSurfaceFeedback.h"
#include "Engine/SkeletalMesh.h"
#include "NiagaraSystem.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCryptoNyanFeedbackProfileTest,"CryptoNyan.Feedback.Profile",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FCryptoNyanFeedbackProfileTest::RunTest(const FString& Parameters) {
    (void)Parameters;
    auto* Profile=NewObject<UCryptoNyanSurfaceFeedbackProfile>();
    TestFalse(TEXT("Empty profile rejected"),Profile->ValidateProfile());
    Profile->TargetMesh=NewObject<USkeletalMesh>(); Profile->FootSockets.Add(TEXT("MappedFoot"));
    FCryptoNyanSurfaceFeedbackCue Cue; Cue.Niagara=NewObject<UNiagaraSystem>(); Profile->Cues.Add(Cue);
    TestTrue(TEXT("Bounded Niagara-only profile"),Profile->ValidateProfile());
    Profile->Cues.Add(Cue); TestFalse(TEXT("Duplicate fallback rejected"),Profile->ValidateProfile());
    Profile->Cues.Pop(); Profile->MaxActiveEffects=17;
    TestFalse(TEXT("Effect budget rejected"),Profile->ValidateProfile());
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCryptoNyanFeedbackPreviewTest,"CryptoNyan.Feedback.NoPreviewEmission",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FCryptoNyanFeedbackPreviewTest::RunTest(const FString& Parameters) {
    (void)Parameters;
    auto* Component=NewObject<UCryptoNyanSurfaceFeedbackComponent>();
    TestFalse(TEXT("No character/game world cannot jump"),Component->NotifyJump());
    TestFalse(TEXT("No game mesh cannot contact"),Component->Contact(nullptr,NAME_None));
    TestEqual(TEXT("Nothing emitted"),Component->EmittedEvents,0);
    TestEqual(TEXT("Rejected calls visible"),Component->RejectedEvents,2);
    return true;
}
#endif
