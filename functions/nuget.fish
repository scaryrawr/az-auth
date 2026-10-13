function nuget --wraps nuget
    __az_artifacts_core run --manager nuget -- $argv
end
