export const environment = {
  production: false,
  // Use proxy path instead of direct URL or in coder use "http://<workspace-name>.coder:<port>" with the port of forward of the api service
  apiUrl: "http://teams-api.127.0.0.1.sslip.io",
  // Base URL of the Argo Rollouts dashboard; app cards deep-link to
  // <rolloutsDashboardUrl>/rollouts/<namespace>/<name>.
  rolloutsDashboardUrl: "http://rollouts.127.0.0.1.sslip.io:8080",
  keycloak: {
    // same as above, but with keycloak forward port
    url: "http://platform-auth.127.0.0.1.sslip.io",
    realm: "teams",
    clientId: "teams-ui",
  },
};
