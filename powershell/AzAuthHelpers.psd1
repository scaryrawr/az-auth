@{
    RootModule = 'AzAuthHelpers.psm1'
    ModuleVersion = '1.0.0'
    GUID = '1a148e5e-76cd-4b9d-a9d1-4116cdb97188'
    Author = 'scaryrawr'
    Description = 'Thin shell entrypoints for the shared Node az-auth-core implementation.'
    PowerShellVersion = '7.3'
    FunctionsToExport = @('npm','npx','pnpm','pnpx','pn','yarn','bun','corepack','dotnet','nuget','rush','Invoke-RushPnpm','write-npm')
    AliasesToExport = @('rush-pnpm')
    CmdletsToExport = @()
    VariablesToExport = @()
}
