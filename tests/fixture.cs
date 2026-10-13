using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;

class Fixture {
    static int Main(string[] args) {
        string name = Path.GetFileNameWithoutExtension(Environment.GetCommandLineArgs()[0]);
        if (name == "python") {
            name = "az";
            args = new List<string>(args).GetRange(2, args.Length - 2).ToArray();
        }
        var env = new Dictionary<string, string>();
        foreach (string key in new[] {"ARTIFACTS_ACCESSTOKEN", "VSS_NUGET_ACCESSTOKEN", "VSS_NUGET_URI_PREFIXES"})
            env[key] = Environment.GetEnvironmentVariable(key);
        var record = new Dictionary<string, object> { {"command", name}, {"args", args}, {"env", env} };
        File.AppendAllText(Environment.GetEnvironmentVariable("TEST_LOG"), new JavaScriptSerializer().Serialize(record) + "\n");
        int status;
        if (name == "az") {
            Console.WriteLine(Environment.GetEnvironmentVariable("TEST_AZ_TOKEN") ?? "fixture-token");
            return Int32.TryParse(Environment.GetEnvironmentVariable("TEST_AZ_STATUS"), out status) ? status : 0;
        }
        if (Environment.GetEnvironmentVariable("TEST_IO") == "yes") {
            Console.Write("manager stdout\n");
            Console.Error.Write("manager stderr\n");
            Console.Write(Console.In.ReadToEnd());
        }
        return Int32.TryParse(Environment.GetEnvironmentVariable("TEST_MANAGER_STATUS"), out status) ? status : 0;
    }
}
