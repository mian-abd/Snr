import { defineRailway, github, project, service } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "web";
export default defineRailway(() => {
  const web = service("web", {
    source: github("mian-abd/Snr"),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/api/v1/health",
    healthcheckTimeout: 60,
    replicas: { "us-west2": 1 },
  });

  return project("adaptive-llm-router", {
    variables: { managed: false },
    resources: [web],
  });
});
