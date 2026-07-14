import { APP_INITIALIZER, NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { ReactiveFormsModule } from '@angular/forms';
import { HttpClientModule, HTTP_INTERCEPTORS } from '@angular/common/http';
import { KeycloakAngularModule, KeycloakService } from 'keycloak-angular';

import { AppComponent } from './app.component';
import { TeamFormComponent } from './components/team-form/team-form.component';
import { TeamListComponent } from './components/team-list/team-list.component';
import { HeaderComponent } from './components/header/header.component';

import { AuthInterceptor } from './interceptors/auth.interceptor';
import keycloakConfig from './config/keycloak.config';

function initializeKeycloak(keycloak: KeycloakService) {
  return () =>
    keycloak
      .init({
        config: keycloakConfig,
        initOptions: {
          onLoad: 'check-sso',
          checkLoginIframe: false,
          // keycloak-js 22 validates the `nonce` claim on the access AND refresh
          // tokens, but Keycloak 26 only sets nonce on the ID token (per OIDC).
          // That version mismatch makes keycloak-js reject init with "Invalid
          // nonce" (undefined) right after a successful token exchange -> blank
          // page. Disabling the nonce check works around it; the auth-code +
          // state parameters still protect the login. (Proper fix: upgrade
          // keycloak-js/keycloak-angular to match Keycloak 26.)
          useNonce: false,
        },
        bearerExcludedUrls: ['/assets'],
      })
      // keycloak-js can reject the post-login init with an undefined reason
      // (silent-SSO / iframe path). Left unhandled it fails APP_INITIALIZER and
      // Angular never bootstraps -> blank page. Swallow it so the app always
      // starts; the token from the code exchange is already set on the service.
      .catch((err) => {
        console.error('Keycloak init did not complete cleanly (continuing):', err);
        return false;
      });
}

@NgModule({
  declarations: [
    AppComponent,
    TeamFormComponent,
    TeamListComponent,
    HeaderComponent
  ],
  imports: [
    BrowserModule,
    ReactiveFormsModule,
    HttpClientModule,
    KeycloakAngularModule
  ],
  providers: [
    {
      provide: APP_INITIALIZER,
      useFactory: initializeKeycloak,
      multi: true,
      deps: [KeycloakService],
    },
    {
      provide: HTTP_INTERCEPTORS,
      useClass: AuthInterceptor,
      multi: true
    }
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }
