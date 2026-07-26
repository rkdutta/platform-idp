export const environment = {
  production: false,
  // Use proxy path instead of direct URL or in coder use "http://<workspace-name>.coder:<port>" with the port of forward of the api service
  apiUrl: "http://teams-api.127.0.0.1.sslip.io",
  // Base URL of the Argo Rollouts dashboard; app cards deep-link to
  // <rolloutsDashboardUrl>/rollouts/<namespace>/<name>.
  rolloutsDashboardUrl: "http://rollouts.127.0.0.1.sslip.io:8080",
  // Base URL of the Argo CD UI - linked from the header so a project-manager
  // or maintainer can create/manage Applications directly (Argo CD's own
  // RBAC, synced from here, decides what they can actually do there).
  argocdUrl: "http://argocd.127.0.0.1.sslip.io:8080",
  keycloak: {
    // same as above, but with keycloak forward port
    url: "http://platform-auth.127.0.0.1.sslip.io",
    realm: "teams",
    clientId: "teams-ui",
  },
};
