// SPDX-License-Identifier: MIT
using UnrealBuildTool;

public class CryptoNyanRuntime : ModuleRules
{
    public CryptoNyanRuntime(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "UMG", "Niagara" });
        PrivateDependencyModuleNames.AddRange(new[] { "Slate", "SlateCore" });
    }
}
