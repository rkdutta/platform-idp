"use strict";
(self["webpackChunkteams_ui"] = self["webpackChunkteams_ui"] || []).push([["main"],{

/***/ 92:
/*!**********************************!*\
  !*** ./src/app/app.component.ts ***!
  \**********************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   AppComponent: () => (/* binding */ AppComponent)
/* harmony export */ });
/* harmony import */ var _Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./node_modules/@babel/runtime/helpers/esm/asyncToGenerator.js */ 9204);
/* harmony import */ var _angular_core__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! @angular/core */ 7580);
/* harmony import */ var _services_auth_service__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./services/auth.service */ 4796);
/* harmony import */ var _angular_common__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! @angular/common */ 316);
/* harmony import */ var _components_team_form_team_form_component__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ./components/team-form/team-form.component */ 3821);
/* harmony import */ var _components_team_list_team_list_component__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./components/team-list/team-list.component */ 5281);
/* harmony import */ var _components_header_header_component__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! ./components/header/header.component */ 385);







function AppComponent_div_0_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](0, "div", 2)(1, "div", 3)(2, "p");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtext"](3, "Loading...");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]()()();
  }
}
function AppComponent_div_1_div_2_main_1_Template(rf, ctx) {
  if (rf & 1) {
    const _r8 = _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵgetCurrentView"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](0, "main", 9)(1, "div", 10)(2, "h2");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtext"](3, "Create New Team");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](4, "app-team-form", 11);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵlistener"]("teamCreated", function AppComponent_div_1_div_2_main_1_Template_app_team_form_teamCreated_4_listener() {
      _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵrestoreView"](_r8);
      const _r6 = _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵreference"](9);
      return _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵresetView"](_r6.loadTeams());
    });
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]()();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](5, "div", 12)(6, "h2");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtext"](7, "Existing Teams");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelement"](8, "app-team-list", null, 13);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]()();
  }
}
function AppComponent_div_1_div_2_div_2_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](0, "div", 14)(1, "h2");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtext"](2, "Access Denied");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](3, "p");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtext"](4, "You don't have permission to manage teams. Please contact your administrator.");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](5, "p");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtext"](6);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]()();
  }
  if (rf & 2) {
    const ctx_r5 = _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵnextContext"](3);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵadvance"](6);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtextInterpolate1"]("Your current roles: ", ctx_r5.authService.getUserRoles().join(", ") || "No roles assigned", "");
  }
}
function AppComponent_div_1_div_2_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](0, "div", 6);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtemplate"](1, AppComponent_div_1_div_2_main_1_Template, 10, 0, "main", 7);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtemplate"](2, AppComponent_div_1_div_2_div_2_Template, 7, 1, "div", 8);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const ctx_r2 = _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵnextContext"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵproperty"]("ngIf", ctx_r2.authService.hasRole("team-leader"));
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵproperty"]("ngIf", !ctx_r2.authService.hasRole("team-leader"));
  }
}
function AppComponent_div_1_div_3_Template(rf, ctx) {
  if (rf & 1) {
    const _r10 = _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵgetCurrentView"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](0, "div", 15)(1, "div", 16)(2, "h2");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtext"](3, "Welcome to Teams Management");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](4, "p");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtext"](5, "Please log in to manage your engineering teams.");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](6, "button", 17);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵlistener"]("click", function AppComponent_div_1_div_3_Template_button_click_6_listener() {
      _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵrestoreView"](_r10);
      const ctx_r9 = _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵnextContext"](2);
      return _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵresetView"](ctx_r9.login());
    });
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtext"](7, " Login with Keycloak ");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]()()();
  }
}
function AppComponent_div_1_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementStart"](0, "div");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelement"](1, "app-header");
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtemplate"](2, AppComponent_div_1_div_2_Template, 3, 2, "div", 4);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtemplate"](3, AppComponent_div_1_div_3_Template, 8, 0, "div", 5);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const ctx_r1 = _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵnextContext"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵadvance"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵproperty"]("ngIf", ctx_r1.isLoggedIn);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵproperty"]("ngIf", !ctx_r1.isLoggedIn);
  }
}
class AppComponent {
  constructor(authService) {
    this.authService = authService;
    this.isLoggedIn = false;
    this.isLoading = true;
  }
  ngOnInit() {
    var _this = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        // Ensure auth state is properly initialized
        yield _this.authService.refreshAuthState();
        _this.isLoggedIn = _this.authService.isLoggedInSync();
      } catch (error) {
        console.error('Failed to initialize app auth state', error);
        _this.isLoggedIn = false;
      } finally {
        _this.isLoading = false;
      }
    })();
  }
  login() {
    var _this2 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        yield _this2.authService.login();
        _this2.isLoggedIn = true;
      } catch (error) {
        console.error('Login failed', error);
      }
    })();
  }
  static {
    this.ɵfac = function AppComponent_Factory(t) {
      return new (t || AppComponent)(_angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵdirectiveInject"](_services_auth_service__WEBPACK_IMPORTED_MODULE_1__.AuthService));
    };
  }
  static {
    this.ɵcmp = /*@__PURE__*/_angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵdefineComponent"]({
      type: AppComponent,
      selectors: [["app-root"]],
      decls: 2,
      vars: 2,
      consts: [["class", "loading-screen", 4, "ngIf"], [4, "ngIf"], [1, "loading-screen"], [1, "loading-spinner"], ["class", "container", 4, "ngIf"], ["class", "login-prompt", 4, "ngIf"], [1, "container"], ["class", "main-content", 4, "ngIf"], ["class", "access-denied", 4, "ngIf"], [1, "main-content"], [1, "form-section"], [3, "teamCreated"], [1, "list-section"], ["teamList", ""], [1, "access-denied"], [1, "login-prompt"], [1, "login-card"], [1, "btn", "btn-primary", "btn-lg", 3, "click"]],
      template: function AppComponent_Template(rf, ctx) {
        if (rf & 1) {
          _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtemplate"](0, AppComponent_div_0_Template, 4, 0, "div", 0);
          _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵtemplate"](1, AppComponent_div_1_Template, 4, 2, "div", 1);
        }
        if (rf & 2) {
          _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵproperty"]("ngIf", ctx.isLoading);
          _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_5__["ɵɵproperty"]("ngIf", !ctx.isLoading);
        }
      },
      dependencies: [_angular_common__WEBPACK_IMPORTED_MODULE_6__.NgIf, _components_team_form_team_form_component__WEBPACK_IMPORTED_MODULE_2__.TeamFormComponent, _components_team_list_team_list_component__WEBPACK_IMPORTED_MODULE_3__.TeamListComponent, _components_header_header_component__WEBPACK_IMPORTED_MODULE_4__.HeaderComponent],
      styles: [".container[_ngcontent-%COMP%] {\n  max-width: 1200px;\n  margin: 0 auto;\n  padding: 20px;\n  min-height: calc(100vh - 200px);\n}\n\n.main-content[_ngcontent-%COMP%] {\n  display: grid;\n  grid-template-columns: 1fr 2fr;\n  gap: 30px;\n  align-items: start;\n}\n\n.form-section[_ngcontent-%COMP%], .list-section[_ngcontent-%COMP%] {\n  background: white;\n  padding: 30px;\n  border-radius: 8px;\n  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);\n}\n\n.form-section[_ngcontent-%COMP%]   h2[_ngcontent-%COMP%], .list-section[_ngcontent-%COMP%]   h2[_ngcontent-%COMP%] {\n  color: #2c3e50;\n  margin-bottom: 20px;\n  font-size: 1.5rem;\n}\n\n.access-denied[_ngcontent-%COMP%] {\n  background: white;\n  padding: 40px;\n  border-radius: 8px;\n  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);\n  text-align: center;\n  color: #e74c3c;\n}\n\n.access-denied[_ngcontent-%COMP%]   h2[_ngcontent-%COMP%] {\n  margin-bottom: 20px;\n  color: #e74c3c;\n}\n\n.access-denied[_ngcontent-%COMP%]   p[_ngcontent-%COMP%] {\n  color: #7f8c8d;\n  margin-bottom: 10px;\n}\n\n.login-prompt[_ngcontent-%COMP%] {\n  display: flex;\n  justify-content: center;\n  align-items: center;\n  min-height: calc(100vh - 200px);\n  padding: 20px;\n}\n\n.login-card[_ngcontent-%COMP%] {\n  background: white;\n  padding: 60px 40px;\n  border-radius: 12px;\n  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);\n  text-align: center;\n  max-width: 400px;\n  width: 100%;\n}\n\n.login-card[_ngcontent-%COMP%]   h2[_ngcontent-%COMP%] {\n  color: #2c3e50;\n  margin-bottom: 20px;\n  font-size: 2rem;\n}\n\n.login-card[_ngcontent-%COMP%]   p[_ngcontent-%COMP%] {\n  color: #7f8c8d;\n  margin-bottom: 30px;\n  font-size: 1.1rem;\n  line-height: 1.5;\n}\n\n.loading-screen[_ngcontent-%COMP%] {\n  display: flex;\n  justify-content: center;\n  align-items: center;\n  min-height: 100vh;\n  background: #f5f5f5;\n}\n\n.loading-spinner[_ngcontent-%COMP%] {\n  text-align: center;\n  color: #7f8c8d;\n}\n\n.loading-spinner[_ngcontent-%COMP%]   p[_ngcontent-%COMP%] {\n  font-size: 18px;\n  margin-top: 20px;\n}\n\n.btn[_ngcontent-%COMP%] {\n  padding: 12px 24px;\n  border: none;\n  border-radius: 6px;\n  font-size: 16px;\n  font-weight: 600;\n  cursor: pointer;\n  transition: all 0.3s ease;\n  display: inline-block;\n  text-decoration: none;\n}\n\n.btn-primary[_ngcontent-%COMP%] {\n  background-color: #3498db;\n  color: white;\n}\n\n.btn-primary[_ngcontent-%COMP%]:hover {\n  background-color: #2980b9;\n  transform: translateY(-1px);\n}\n\n.btn-lg[_ngcontent-%COMP%] {\n  padding: 16px 32px;\n  font-size: 18px;\n}\n\n@media (max-width: 768px) {\n  .main-content[_ngcontent-%COMP%] {\n    grid-template-columns: 1fr;\n    gap: 20px;\n  }\n  \n  .login-card[_ngcontent-%COMP%] {\n    padding: 40px 20px;\n  }\n  \n  .login-card[_ngcontent-%COMP%]   h2[_ngcontent-%COMP%] {\n    font-size: 1.5rem;\n  }\n}\n\n/*# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbIndlYnBhY2s6Ly8uL3NyYy9hcHAvYXBwLmNvbXBvbmVudC5jc3MiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7RUFDRSxpQkFBaUI7RUFDakIsY0FBYztFQUNkLGFBQWE7RUFDYiwrQkFBK0I7QUFDakM7O0FBRUE7RUFDRSxhQUFhO0VBQ2IsOEJBQThCO0VBQzlCLFNBQVM7RUFDVCxrQkFBa0I7QUFDcEI7O0FBRUE7RUFDRSxpQkFBaUI7RUFDakIsYUFBYTtFQUNiLGtCQUFrQjtFQUNsQix3Q0FBd0M7QUFDMUM7O0FBRUE7RUFDRSxjQUFjO0VBQ2QsbUJBQW1CO0VBQ25CLGlCQUFpQjtBQUNuQjs7QUFFQTtFQUNFLGlCQUFpQjtFQUNqQixhQUFhO0VBQ2Isa0JBQWtCO0VBQ2xCLHdDQUF3QztFQUN4QyxrQkFBa0I7RUFDbEIsY0FBYztBQUNoQjs7QUFFQTtFQUNFLG1CQUFtQjtFQUNuQixjQUFjO0FBQ2hCOztBQUVBO0VBQ0UsY0FBYztFQUNkLG1CQUFtQjtBQUNyQjs7QUFFQTtFQUNFLGFBQWE7RUFDYix1QkFBdUI7RUFDdkIsbUJBQW1CO0VBQ25CLCtCQUErQjtFQUMvQixhQUFhO0FBQ2Y7O0FBRUE7RUFDRSxpQkFBaUI7RUFDakIsa0JBQWtCO0VBQ2xCLG1CQUFtQjtFQUNuQiwwQ0FBMEM7RUFDMUMsa0JBQWtCO0VBQ2xCLGdCQUFnQjtFQUNoQixXQUFXO0FBQ2I7O0FBRUE7RUFDRSxjQUFjO0VBQ2QsbUJBQW1CO0VBQ25CLGVBQWU7QUFDakI7O0FBRUE7RUFDRSxjQUFjO0VBQ2QsbUJBQW1CO0VBQ25CLGlCQUFpQjtFQUNqQixnQkFBZ0I7QUFDbEI7O0FBRUE7RUFDRSxhQUFhO0VBQ2IsdUJBQXVCO0VBQ3ZCLG1CQUFtQjtFQUNuQixpQkFBaUI7RUFDakIsbUJBQW1CO0FBQ3JCOztBQUVBO0VBQ0Usa0JBQWtCO0VBQ2xCLGNBQWM7QUFDaEI7O0FBRUE7RUFDRSxlQUFlO0VBQ2YsZ0JBQWdCO0FBQ2xCOztBQUVBO0VBQ0Usa0JBQWtCO0VBQ2xCLFlBQVk7RUFDWixrQkFBa0I7RUFDbEIsZUFBZTtFQUNmLGdCQUFnQjtFQUNoQixlQUFlO0VBQ2YseUJBQXlCO0VBQ3pCLHFCQUFxQjtFQUNyQixxQkFBcUI7QUFDdkI7O0FBRUE7RUFDRSx5QkFBeUI7RUFDekIsWUFBWTtBQUNkOztBQUVBO0VBQ0UseUJBQXlCO0VBQ3pCLDJCQUEyQjtBQUM3Qjs7QUFFQTtFQUNFLGtCQUFrQjtFQUNsQixlQUFlO0FBQ2pCOztBQUVBO0VBQ0U7SUFDRSwwQkFBMEI7SUFDMUIsU0FBUztFQUNYOztFQUVBO0lBQ0Usa0JBQWtCO0VBQ3BCOztFQUVBO0lBQ0UsaUJBQWlCO0VBQ25CO0FBQ0YiLCJzb3VyY2VzQ29udGVudCI6WyIuY29udGFpbmVyIHtcbiAgbWF4LXdpZHRoOiAxMjAwcHg7XG4gIG1hcmdpbjogMCBhdXRvO1xuICBwYWRkaW5nOiAyMHB4O1xuICBtaW4taGVpZ2h0OiBjYWxjKDEwMHZoIC0gMjAwcHgpO1xufVxuXG4ubWFpbi1jb250ZW50IHtcbiAgZGlzcGxheTogZ3JpZDtcbiAgZ3JpZC10ZW1wbGF0ZS1jb2x1bW5zOiAxZnIgMmZyO1xuICBnYXA6IDMwcHg7XG4gIGFsaWduLWl0ZW1zOiBzdGFydDtcbn1cblxuLmZvcm0tc2VjdGlvbiwgLmxpc3Qtc2VjdGlvbiB7XG4gIGJhY2tncm91bmQ6IHdoaXRlO1xuICBwYWRkaW5nOiAzMHB4O1xuICBib3JkZXItcmFkaXVzOiA4cHg7XG4gIGJveC1zaGFkb3c6IDAgMnB4IDRweCByZ2JhKDAsIDAsIDAsIDAuMSk7XG59XG5cbi5mb3JtLXNlY3Rpb24gaDIsIC5saXN0LXNlY3Rpb24gaDIge1xuICBjb2xvcjogIzJjM2U1MDtcbiAgbWFyZ2luLWJvdHRvbTogMjBweDtcbiAgZm9udC1zaXplOiAxLjVyZW07XG59XG5cbi5hY2Nlc3MtZGVuaWVkIHtcbiAgYmFja2dyb3VuZDogd2hpdGU7XG4gIHBhZGRpbmc6IDQwcHg7XG4gIGJvcmRlci1yYWRpdXM6IDhweDtcbiAgYm94LXNoYWRvdzogMCAycHggNHB4IHJnYmEoMCwgMCwgMCwgMC4xKTtcbiAgdGV4dC1hbGlnbjogY2VudGVyO1xuICBjb2xvcjogI2U3NGMzYztcbn1cblxuLmFjY2Vzcy1kZW5pZWQgaDIge1xuICBtYXJnaW4tYm90dG9tOiAyMHB4O1xuICBjb2xvcjogI2U3NGMzYztcbn1cblxuLmFjY2Vzcy1kZW5pZWQgcCB7XG4gIGNvbG9yOiAjN2Y4YzhkO1xuICBtYXJnaW4tYm90dG9tOiAxMHB4O1xufVxuXG4ubG9naW4tcHJvbXB0IHtcbiAgZGlzcGxheTogZmxleDtcbiAganVzdGlmeS1jb250ZW50OiBjZW50ZXI7XG4gIGFsaWduLWl0ZW1zOiBjZW50ZXI7XG4gIG1pbi1oZWlnaHQ6IGNhbGMoMTAwdmggLSAyMDBweCk7XG4gIHBhZGRpbmc6IDIwcHg7XG59XG5cbi5sb2dpbi1jYXJkIHtcbiAgYmFja2dyb3VuZDogd2hpdGU7XG4gIHBhZGRpbmc6IDYwcHggNDBweDtcbiAgYm9yZGVyLXJhZGl1czogMTJweDtcbiAgYm94LXNoYWRvdzogMCA0cHggMTJweCByZ2JhKDAsIDAsIDAsIDAuMTUpO1xuICB0ZXh0LWFsaWduOiBjZW50ZXI7XG4gIG1heC13aWR0aDogNDAwcHg7XG4gIHdpZHRoOiAxMDAlO1xufVxuXG4ubG9naW4tY2FyZCBoMiB7XG4gIGNvbG9yOiAjMmMzZTUwO1xuICBtYXJnaW4tYm90dG9tOiAyMHB4O1xuICBmb250LXNpemU6IDJyZW07XG59XG5cbi5sb2dpbi1jYXJkIHAge1xuICBjb2xvcjogIzdmOGM4ZDtcbiAgbWFyZ2luLWJvdHRvbTogMzBweDtcbiAgZm9udC1zaXplOiAxLjFyZW07XG4gIGxpbmUtaGVpZ2h0OiAxLjU7XG59XG5cbi5sb2FkaW5nLXNjcmVlbiB7XG4gIGRpc3BsYXk6IGZsZXg7XG4gIGp1c3RpZnktY29udGVudDogY2VudGVyO1xuICBhbGlnbi1pdGVtczogY2VudGVyO1xuICBtaW4taGVpZ2h0OiAxMDB2aDtcbiAgYmFja2dyb3VuZDogI2Y1ZjVmNTtcbn1cblxuLmxvYWRpbmctc3Bpbm5lciB7XG4gIHRleHQtYWxpZ246IGNlbnRlcjtcbiAgY29sb3I6ICM3ZjhjOGQ7XG59XG5cbi5sb2FkaW5nLXNwaW5uZXIgcCB7XG4gIGZvbnQtc2l6ZTogMThweDtcbiAgbWFyZ2luLXRvcDogMjBweDtcbn1cblxuLmJ0biB7XG4gIHBhZGRpbmc6IDEycHggMjRweDtcbiAgYm9yZGVyOiBub25lO1xuICBib3JkZXItcmFkaXVzOiA2cHg7XG4gIGZvbnQtc2l6ZTogMTZweDtcbiAgZm9udC13ZWlnaHQ6IDYwMDtcbiAgY3Vyc29yOiBwb2ludGVyO1xuICB0cmFuc2l0aW9uOiBhbGwgMC4zcyBlYXNlO1xuICBkaXNwbGF5OiBpbmxpbmUtYmxvY2s7XG4gIHRleHQtZGVjb3JhdGlvbjogbm9uZTtcbn1cblxuLmJ0bi1wcmltYXJ5IHtcbiAgYmFja2dyb3VuZC1jb2xvcjogIzM0OThkYjtcbiAgY29sb3I6IHdoaXRlO1xufVxuXG4uYnRuLXByaW1hcnk6aG92ZXIge1xuICBiYWNrZ3JvdW5kLWNvbG9yOiAjMjk4MGI5O1xuICB0cmFuc2Zvcm06IHRyYW5zbGF0ZVkoLTFweCk7XG59XG5cbi5idG4tbGcge1xuICBwYWRkaW5nOiAxNnB4IDMycHg7XG4gIGZvbnQtc2l6ZTogMThweDtcbn1cblxuQG1lZGlhIChtYXgtd2lkdGg6IDc2OHB4KSB7XG4gIC5tYWluLWNvbnRlbnQge1xuICAgIGdyaWQtdGVtcGxhdGUtY29sdW1uczogMWZyO1xuICAgIGdhcDogMjBweDtcbiAgfVxuICBcbiAgLmxvZ2luLWNhcmQge1xuICAgIHBhZGRpbmc6IDQwcHggMjBweDtcbiAgfVxuICBcbiAgLmxvZ2luLWNhcmQgaDIge1xuICAgIGZvbnQtc2l6ZTogMS41cmVtO1xuICB9XG59XG4iXSwic291cmNlUm9vdCI6IiJ9 */"]
    });
  }
}

/***/ }),

/***/ 635:
/*!*******************************!*\
  !*** ./src/app/app.module.ts ***!
  \*******************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   AppModule: () => (/* binding */ AppModule)
/* harmony export */ });
/* harmony import */ var _angular_core__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! @angular/core */ 7580);
/* harmony import */ var _angular_platform_browser__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(/*! @angular/platform-browser */ 436);
/* harmony import */ var _angular_forms__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(/*! @angular/forms */ 4456);
/* harmony import */ var _angular_common_http__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(/*! @angular/common/http */ 6443);
/* harmony import */ var keycloak_angular__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! keycloak-angular */ 9837);
/* harmony import */ var _app_component__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./app.component */ 92);
/* harmony import */ var _components_team_form_team_form_component__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./components/team-form/team-form.component */ 3821);
/* harmony import */ var _components_team_list_team_list_component__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ./components/team-list/team-list.component */ 5281);
/* harmony import */ var _components_header_header_component__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./components/header/header.component */ 385);
/* harmony import */ var _interceptors_auth_interceptor__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! ./interceptors/auth.interceptor */ 472);
/* harmony import */ var _config_keycloak_config__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./config/keycloak.config */ 1250);












function initializeKeycloak(keycloak) {
  return () => keycloak.init({
    config: _config_keycloak_config__WEBPACK_IMPORTED_MODULE_5__["default"],
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
      useNonce: false
    },
    bearerExcludedUrls: ['/assets']
  })
  // keycloak-js can reject the post-login init with an undefined reason
  // (silent-SSO / iframe path). Left unhandled it fails APP_INITIALIZER and
  // Angular never bootstraps -> blank page. Swallow it so the app always
  // starts; the token from the code exchange is already set on the service.
  .catch(err => {
    console.error('Keycloak init did not complete cleanly (continuing):', err);
    return false;
  });
}
class AppModule {
  static {
    this.ɵfac = function AppModule_Factory(t) {
      return new (t || AppModule)();
    };
  }
  static {
    this.ɵmod = /*@__PURE__*/_angular_core__WEBPACK_IMPORTED_MODULE_6__["ɵɵdefineNgModule"]({
      type: AppModule,
      bootstrap: [_app_component__WEBPACK_IMPORTED_MODULE_0__.AppComponent]
    });
  }
  static {
    this.ɵinj = /*@__PURE__*/_angular_core__WEBPACK_IMPORTED_MODULE_6__["ɵɵdefineInjector"]({
      providers: [{
        provide: _angular_core__WEBPACK_IMPORTED_MODULE_6__.APP_INITIALIZER,
        useFactory: initializeKeycloak,
        multi: true,
        deps: [keycloak_angular__WEBPACK_IMPORTED_MODULE_7__.KeycloakService]
      }, {
        provide: _angular_common_http__WEBPACK_IMPORTED_MODULE_8__.HTTP_INTERCEPTORS,
        useClass: _interceptors_auth_interceptor__WEBPACK_IMPORTED_MODULE_4__.AuthInterceptor,
        multi: true
      }],
      imports: [_angular_platform_browser__WEBPACK_IMPORTED_MODULE_9__.BrowserModule, _angular_forms__WEBPACK_IMPORTED_MODULE_10__.ReactiveFormsModule, _angular_common_http__WEBPACK_IMPORTED_MODULE_8__.HttpClientModule, keycloak_angular__WEBPACK_IMPORTED_MODULE_7__.KeycloakAngularModule]
    });
  }
}
(function () {
  (typeof ngJitMode === "undefined" || ngJitMode) && _angular_core__WEBPACK_IMPORTED_MODULE_6__["ɵɵsetNgModuleScope"](AppModule, {
    declarations: [_app_component__WEBPACK_IMPORTED_MODULE_0__.AppComponent, _components_team_form_team_form_component__WEBPACK_IMPORTED_MODULE_1__.TeamFormComponent, _components_team_list_team_list_component__WEBPACK_IMPORTED_MODULE_2__.TeamListComponent, _components_header_header_component__WEBPACK_IMPORTED_MODULE_3__.HeaderComponent],
    imports: [_angular_platform_browser__WEBPACK_IMPORTED_MODULE_9__.BrowserModule, _angular_forms__WEBPACK_IMPORTED_MODULE_10__.ReactiveFormsModule, _angular_common_http__WEBPACK_IMPORTED_MODULE_8__.HttpClientModule, keycloak_angular__WEBPACK_IMPORTED_MODULE_7__.KeycloakAngularModule]
  });
})();

/***/ }),

/***/ 385:
/*!*******************************************************!*\
  !*** ./src/app/components/header/header.component.ts ***!
  \*******************************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   HeaderComponent: () => (/* binding */ HeaderComponent)
/* harmony export */ });
/* harmony import */ var _Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./node_modules/@babel/runtime/helpers/esm/asyncToGenerator.js */ 9204);
/* harmony import */ var _angular_core__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @angular/core */ 7580);
/* harmony import */ var _services_auth_service__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ../../services/auth.service */ 4796);
/* harmony import */ var _angular_common__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! @angular/common */ 316);




function HeaderComponent_div_7_div_4_span_1_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementStart"](0, "span", 12);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const role_r4 = ctx.$implicit;
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtextInterpolate1"](" ", role_r4, " ");
  }
}
function HeaderComponent_div_7_div_4_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementStart"](0, "div", 10);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtemplate"](1, HeaderComponent_div_7_div_4_span_1_Template, 2, 1, "span", 11);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const ctx_r2 = _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵnextContext"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵproperty"]("ngForOf", ctx_r2.userRoles);
  }
}
function HeaderComponent_div_7_Template(rf, ctx) {
  if (rf & 1) {
    const _r6 = _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵgetCurrentView"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementStart"](0, "div", 5)(1, "div", 6)(2, "span", 7);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtext"](3);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtemplate"](4, HeaderComponent_div_7_div_4_Template, 2, 1, "div", 8);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementStart"](5, "button", 9);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵlistener"]("click", function HeaderComponent_div_7_Template_button_click_5_listener() {
      _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵrestoreView"](_r6);
      const ctx_r5 = _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵnextContext"]();
      return _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵresetView"](ctx_r5.logout());
    });
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtext"](6, " Logout ");
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementEnd"]()();
  }
  if (rf & 2) {
    const ctx_r0 = _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵnextContext"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵadvance"](3);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtextInterpolate1"](" Welcome, ", (ctx_r0.userProfile == null ? null : ctx_r0.userProfile.firstName) || (ctx_r0.userProfile == null ? null : ctx_r0.userProfile.username), "! ");
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵproperty"]("ngIf", ctx_r0.userRoles.length > 0);
  }
}
function HeaderComponent_div_8_Template(rf, ctx) {
  if (rf & 1) {
    const _r8 = _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵgetCurrentView"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementStart"](0, "div", 5)(1, "button", 13);
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵlistener"]("click", function HeaderComponent_div_8_Template_button_click_1_listener() {
      _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵrestoreView"](_r8);
      const ctx_r7 = _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵnextContext"]();
      return _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵresetView"](ctx_r7.login());
    });
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtext"](2, " Login ");
    _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementEnd"]()();
  }
}
class HeaderComponent {
  constructor(authService) {
    this.authService = authService;
    this.userProfile = null;
    this.isLoggedIn = false;
    this.userRoles = [];
    this.isLoading = true;
  }
  ngOnInit() {
    var _this = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      const tokenInfo = _this.authService.getUserInfoFromToken();
      console.log(tokenInfo);
      try {
        // Ensure auth state is refreshed
        yield _this.authService.refreshAuthState();
        _this.isLoggedIn = _this.authService.isLoggedInSync();
        if (_this.isLoggedIn) {
          try {
            // this.userProfile = await this.authService.loadUserProfile();
            // this.userRoles = this.authService.getUserRoles();
            _this.userProfile = tokenInfo;
            _this.userRoles = tokenInfo.roles;
          } catch (error) {
            console.error("Failed to load user profile", error);
          }
        }
      } catch (error) {
        console.error("Failed to initialize auth state", error);
      } finally {
        _this.isLoading = false;
      }
    })();
  }
  login() {
    var _this2 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        yield _this2.authService.login();
      } catch (error) {
        console.error("Login failed", error);
      }
    })();
  }
  logout() {
    var _this3 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        yield _this3.authService.logout();
        _this3.isLoggedIn = false;
        _this3.userProfile = null;
        _this3.userRoles = [];
      } catch (error) {
        console.error("Logout failed", error);
      }
    })();
  }
  get canManageTeams() {
    return this.authService.hasRole("team-leader") || this.authService.hasRole("admin");
  }
  static {
    this.ɵfac = function HeaderComponent_Factory(t) {
      return new (t || HeaderComponent)(_angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵdirectiveInject"](_services_auth_service__WEBPACK_IMPORTED_MODULE_1__.AuthService));
    };
  }
  static {
    this.ɵcmp = /*@__PURE__*/_angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵdefineComponent"]({
      type: HeaderComponent,
      selectors: [["app-header"]],
      decls: 9,
      vars: 2,
      consts: [[1, "header"], [1, "header-content"], [1, "header-left"], [1, "subtitle"], ["class", "header-right", 4, "ngIf"], [1, "header-right"], [1, "user-info"], [1, "welcome-text"], ["class", "user-roles", 4, "ngIf"], [1, "btn", "btn-secondary", 3, "click"], [1, "user-roles"], ["class", "role-badge", 4, "ngFor", "ngForOf"], [1, "role-badge"], [1, "btn", "btn-primary", 3, "click"]],
      template: function HeaderComponent_Template(rf, ctx) {
        if (rf & 1) {
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementStart"](0, "header", 0)(1, "div", 1)(2, "div", 2)(3, "h1");
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtext"](4, "Engineering Platform");
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementEnd"]();
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementStart"](5, "p", 3);
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtext"](6, "Teams Management");
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementEnd"]()();
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtemplate"](7, HeaderComponent_div_7_Template, 7, 2, "div", 4);
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵtemplate"](8, HeaderComponent_div_8_Template, 3, 0, "div", 4);
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵelementEnd"]()();
        }
        if (rf & 2) {
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵadvance"](7);
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵproperty"]("ngIf", ctx.isLoggedIn);
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_2__["ɵɵproperty"]("ngIf", !ctx.isLoggedIn);
        }
      },
      dependencies: [_angular_common__WEBPACK_IMPORTED_MODULE_3__.NgForOf, _angular_common__WEBPACK_IMPORTED_MODULE_3__.NgIf],
      styles: [".header[_ngcontent-%COMP%] {\n  background: white;\n  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);\n  padding: 20px 0;\n  margin-bottom: 40px;\n}\n\n.header-content[_ngcontent-%COMP%] {\n  max-width: 1200px;\n  margin: 0 auto;\n  padding: 0 20px;\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n}\n\n.header-left[_ngcontent-%COMP%]   h1[_ngcontent-%COMP%] {\n  color: #2c3e50;\n  font-size: 2rem;\n  margin: 0;\n}\n\n.subtitle[_ngcontent-%COMP%] {\n  color: #7f8c8d;\n  font-size: 1rem;\n  margin: 0;\n}\n\n.header-right[_ngcontent-%COMP%] {\n  display: flex;\n  align-items: center;\n  gap: 20px;\n}\n\n.user-info[_ngcontent-%COMP%] {\n  text-align: right;\n}\n\n.welcome-text[_ngcontent-%COMP%] {\n  color: #2c3e50;\n  font-weight: 500;\n  display: block;\n  margin-bottom: 5px;\n}\n\n.user-roles[_ngcontent-%COMP%] {\n  display: flex;\n  gap: 5px;\n  justify-content: flex-end;\n}\n\n.role-badge[_ngcontent-%COMP%] {\n  background: #3498db;\n  color: white;\n  padding: 2px 8px;\n  border-radius: 12px;\n  font-size: 12px;\n  text-transform: uppercase;\n}\n\n.btn[_ngcontent-%COMP%] {\n  padding: 10px 20px;\n  border: none;\n  border-radius: 6px;\n  font-size: 14px;\n  font-weight: 600;\n  cursor: pointer;\n  transition: all 0.3s ease;\n}\n\n.btn-primary[_ngcontent-%COMP%] {\n  background-color: #3498db;\n  color: white;\n}\n\n.btn-primary[_ngcontent-%COMP%]:hover {\n  background-color: #2980b9;\n}\n\n.btn-secondary[_ngcontent-%COMP%] {\n  background-color: #95a5a6;\n  color: white;\n}\n\n.btn-secondary[_ngcontent-%COMP%]:hover {\n  background-color: #7f8c8d;\n}\n\n@media (max-width: 768px) {\n  .header-content[_ngcontent-%COMP%] {\n    flex-direction: column;\n    gap: 15px;\n    text-align: center;\n  }\n  \n  .user-info[_ngcontent-%COMP%] {\n    text-align: center;\n  }\n  \n  .user-roles[_ngcontent-%COMP%] {\n    justify-content: center;\n  }\n}\n\n/*# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbIndlYnBhY2s6Ly8uL3NyYy9hcHAvY29tcG9uZW50cy9oZWFkZXIvaGVhZGVyLmNvbXBvbmVudC5jc3MiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7RUFDRSxpQkFBaUI7RUFDakIsd0NBQXdDO0VBQ3hDLGVBQWU7RUFDZixtQkFBbUI7QUFDckI7O0FBRUE7RUFDRSxpQkFBaUI7RUFDakIsY0FBYztFQUNkLGVBQWU7RUFDZixhQUFhO0VBQ2IsOEJBQThCO0VBQzlCLG1CQUFtQjtBQUNyQjs7QUFFQTtFQUNFLGNBQWM7RUFDZCxlQUFlO0VBQ2YsU0FBUztBQUNYOztBQUVBO0VBQ0UsY0FBYztFQUNkLGVBQWU7RUFDZixTQUFTO0FBQ1g7O0FBRUE7RUFDRSxhQUFhO0VBQ2IsbUJBQW1CO0VBQ25CLFNBQVM7QUFDWDs7QUFFQTtFQUNFLGlCQUFpQjtBQUNuQjs7QUFFQTtFQUNFLGNBQWM7RUFDZCxnQkFBZ0I7RUFDaEIsY0FBYztFQUNkLGtCQUFrQjtBQUNwQjs7QUFFQTtFQUNFLGFBQWE7RUFDYixRQUFRO0VBQ1IseUJBQXlCO0FBQzNCOztBQUVBO0VBQ0UsbUJBQW1CO0VBQ25CLFlBQVk7RUFDWixnQkFBZ0I7RUFDaEIsbUJBQW1CO0VBQ25CLGVBQWU7RUFDZix5QkFBeUI7QUFDM0I7O0FBRUE7RUFDRSxrQkFBa0I7RUFDbEIsWUFBWTtFQUNaLGtCQUFrQjtFQUNsQixlQUFlO0VBQ2YsZ0JBQWdCO0VBQ2hCLGVBQWU7RUFDZix5QkFBeUI7QUFDM0I7O0FBRUE7RUFDRSx5QkFBeUI7RUFDekIsWUFBWTtBQUNkOztBQUVBO0VBQ0UseUJBQXlCO0FBQzNCOztBQUVBO0VBQ0UseUJBQXlCO0VBQ3pCLFlBQVk7QUFDZDs7QUFFQTtFQUNFLHlCQUF5QjtBQUMzQjs7QUFFQTtFQUNFO0lBQ0Usc0JBQXNCO0lBQ3RCLFNBQVM7SUFDVCxrQkFBa0I7RUFDcEI7O0VBRUE7SUFDRSxrQkFBa0I7RUFDcEI7O0VBRUE7SUFDRSx1QkFBdUI7RUFDekI7QUFDRiIsInNvdXJjZXNDb250ZW50IjpbIi5oZWFkZXIge1xuICBiYWNrZ3JvdW5kOiB3aGl0ZTtcbiAgYm94LXNoYWRvdzogMCAycHggNHB4IHJnYmEoMCwgMCwgMCwgMC4xKTtcbiAgcGFkZGluZzogMjBweCAwO1xuICBtYXJnaW4tYm90dG9tOiA0MHB4O1xufVxuXG4uaGVhZGVyLWNvbnRlbnQge1xuICBtYXgtd2lkdGg6IDEyMDBweDtcbiAgbWFyZ2luOiAwIGF1dG87XG4gIHBhZGRpbmc6IDAgMjBweDtcbiAgZGlzcGxheTogZmxleDtcbiAganVzdGlmeS1jb250ZW50OiBzcGFjZS1iZXR3ZWVuO1xuICBhbGlnbi1pdGVtczogY2VudGVyO1xufVxuXG4uaGVhZGVyLWxlZnQgaDEge1xuICBjb2xvcjogIzJjM2U1MDtcbiAgZm9udC1zaXplOiAycmVtO1xuICBtYXJnaW46IDA7XG59XG5cbi5zdWJ0aXRsZSB7XG4gIGNvbG9yOiAjN2Y4YzhkO1xuICBmb250LXNpemU6IDFyZW07XG4gIG1hcmdpbjogMDtcbn1cblxuLmhlYWRlci1yaWdodCB7XG4gIGRpc3BsYXk6IGZsZXg7XG4gIGFsaWduLWl0ZW1zOiBjZW50ZXI7XG4gIGdhcDogMjBweDtcbn1cblxuLnVzZXItaW5mbyB7XG4gIHRleHQtYWxpZ246IHJpZ2h0O1xufVxuXG4ud2VsY29tZS10ZXh0IHtcbiAgY29sb3I6ICMyYzNlNTA7XG4gIGZvbnQtd2VpZ2h0OiA1MDA7XG4gIGRpc3BsYXk6IGJsb2NrO1xuICBtYXJnaW4tYm90dG9tOiA1cHg7XG59XG5cbi51c2VyLXJvbGVzIHtcbiAgZGlzcGxheTogZmxleDtcbiAgZ2FwOiA1cHg7XG4gIGp1c3RpZnktY29udGVudDogZmxleC1lbmQ7XG59XG5cbi5yb2xlLWJhZGdlIHtcbiAgYmFja2dyb3VuZDogIzM0OThkYjtcbiAgY29sb3I6IHdoaXRlO1xuICBwYWRkaW5nOiAycHggOHB4O1xuICBib3JkZXItcmFkaXVzOiAxMnB4O1xuICBmb250LXNpemU6IDEycHg7XG4gIHRleHQtdHJhbnNmb3JtOiB1cHBlcmNhc2U7XG59XG5cbi5idG4ge1xuICBwYWRkaW5nOiAxMHB4IDIwcHg7XG4gIGJvcmRlcjogbm9uZTtcbiAgYm9yZGVyLXJhZGl1czogNnB4O1xuICBmb250LXNpemU6IDE0cHg7XG4gIGZvbnQtd2VpZ2h0OiA2MDA7XG4gIGN1cnNvcjogcG9pbnRlcjtcbiAgdHJhbnNpdGlvbjogYWxsIDAuM3MgZWFzZTtcbn1cblxuLmJ0bi1wcmltYXJ5IHtcbiAgYmFja2dyb3VuZC1jb2xvcjogIzM0OThkYjtcbiAgY29sb3I6IHdoaXRlO1xufVxuXG4uYnRuLXByaW1hcnk6aG92ZXIge1xuICBiYWNrZ3JvdW5kLWNvbG9yOiAjMjk4MGI5O1xufVxuXG4uYnRuLXNlY29uZGFyeSB7XG4gIGJhY2tncm91bmQtY29sb3I6ICM5NWE1YTY7XG4gIGNvbG9yOiB3aGl0ZTtcbn1cblxuLmJ0bi1zZWNvbmRhcnk6aG92ZXIge1xuICBiYWNrZ3JvdW5kLWNvbG9yOiAjN2Y4YzhkO1xufVxuXG5AbWVkaWEgKG1heC13aWR0aDogNzY4cHgpIHtcbiAgLmhlYWRlci1jb250ZW50IHtcbiAgICBmbGV4LWRpcmVjdGlvbjogY29sdW1uO1xuICAgIGdhcDogMTVweDtcbiAgICB0ZXh0LWFsaWduOiBjZW50ZXI7XG4gIH1cbiAgXG4gIC51c2VyLWluZm8ge1xuICAgIHRleHQtYWxpZ246IGNlbnRlcjtcbiAgfVxuICBcbiAgLnVzZXItcm9sZXMge1xuICAgIGp1c3RpZnktY29udGVudDogY2VudGVyO1xuICB9XG59XG4iXSwic291cmNlUm9vdCI6IiJ9 */"]
    });
  }
}

/***/ }),

/***/ 3821:
/*!*************************************************************!*\
  !*** ./src/app/components/team-form/team-form.component.ts ***!
  \*************************************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   TeamFormComponent: () => (/* binding */ TeamFormComponent)
/* harmony export */ });
/* harmony import */ var _angular_core__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @angular/core */ 7580);
/* harmony import */ var _angular_forms__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @angular/forms */ 4456);
/* harmony import */ var _services_teams_service__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../../services/teams.service */ 5092);
/* harmony import */ var _angular_common__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! @angular/common */ 316);
// src/app/components/team-form/team-form.component.ts






function TeamFormComponent_div_5_span_1_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "span");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1, "Team name is required");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
}
function TeamFormComponent_div_5_span_2_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "span");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1, "Team name must be at least 2 characters");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
}
function TeamFormComponent_div_5_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 7);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](1, TeamFormComponent_div_5_span_1_Template, 2, 0, "span", 6);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](2, TeamFormComponent_div_5_span_2_Template, 2, 0, "span", 6);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const ctx_r0 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx_r0.name == null ? null : ctx_r0.name.errors == null ? null : ctx_r0.name.errors["required"]);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx_r0.name == null ? null : ctx_r0.name.errors == null ? null : ctx_r0.name.errors["minlength"]);
  }
}
function TeamFormComponent_div_6_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 7);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const ctx_r1 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"](" ", ctx_r1.errorMessage, " ");
  }
}
function TeamFormComponent_span_8_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "span");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1, "Creating...");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
}
function TeamFormComponent_span_9_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "span");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1, "Create Team");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
}
class TeamFormComponent {
  constructor(fb, teamsService) {
    this.fb = fb;
    this.teamsService = teamsService;
    this.teamCreated = new _angular_core__WEBPACK_IMPORTED_MODULE_1__.EventEmitter();
    this.isSubmitting = false;
    this.errorMessage = '';
    this.teamForm = this.fb.group({
      name: ['', [_angular_forms__WEBPACK_IMPORTED_MODULE_2__.Validators.required, _angular_forms__WEBPACK_IMPORTED_MODULE_2__.Validators.minLength(2)]]
    });
  }
  onSubmit() {
    if (this.teamForm.valid) {
      this.isSubmitting = true;
      this.errorMessage = '';
      const teamData = {
        name: this.teamForm.value.name.trim()
      };
      this.teamsService.createTeam(teamData).subscribe({
        next: () => {
          this.teamForm.reset();
          this.teamCreated.emit();
          this.isSubmitting = false;
        },
        error: error => {
          this.errorMessage = error;
          this.isSubmitting = false;
        }
      });
    }
  }
  get name() {
    return this.teamForm.get('name');
  }
  static {
    this.ɵfac = function TeamFormComponent_Factory(t) {
      return new (t || TeamFormComponent)(_angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵdirectiveInject"](_angular_forms__WEBPACK_IMPORTED_MODULE_2__.FormBuilder), _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵdirectiveInject"](_services_teams_service__WEBPACK_IMPORTED_MODULE_0__.TeamsService));
    };
  }
  static {
    this.ɵcmp = /*@__PURE__*/_angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵdefineComponent"]({
      type: TeamFormComponent,
      selectors: [["app-team-form"]],
      outputs: {
        teamCreated: "teamCreated"
      },
      decls: 10,
      vars: 8,
      consts: [[1, "team-form", 3, "formGroup", "ngSubmit"], [1, "form-group"], ["for", "name"], ["type", "text", "id", "name", "formControlName", "name", "placeholder", "Enter team name", 1, "form-control"], ["class", "error-message", 4, "ngIf"], ["type", "submit", 1, "btn", "btn-primary", 3, "disabled"], [4, "ngIf"], [1, "error-message"]],
      template: function TeamFormComponent_Template(rf, ctx) {
        if (rf & 1) {
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "form", 0);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵlistener"]("ngSubmit", function TeamFormComponent_Template_form_ngSubmit_0_listener() {
            return ctx.onSubmit();
          });
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](1, "div", 1)(2, "label", 2);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](3, "Team Name");
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelement"](4, "input", 3);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](5, TeamFormComponent_div_5_Template, 3, 2, "div", 4);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](6, TeamFormComponent_div_6_Template, 2, 1, "div", 4);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](7, "button", 5);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](8, TeamFormComponent_span_8_Template, 2, 0, "span", 6);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](9, TeamFormComponent_span_9_Template, 2, 0, "span", 6);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]()();
        }
        if (rf & 2) {
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("formGroup", ctx.teamForm);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](4);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵclassProp"]("invalid", (ctx.name == null ? null : ctx.name.invalid) && (ctx.name == null ? null : ctx.name.touched));
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", (ctx.name == null ? null : ctx.name.invalid) && (ctx.name == null ? null : ctx.name.touched));
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx.errorMessage);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("disabled", ctx.teamForm.invalid || ctx.isSubmitting);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx.isSubmitting);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", !ctx.isSubmitting);
        }
      },
      dependencies: [_angular_common__WEBPACK_IMPORTED_MODULE_3__.NgIf, _angular_forms__WEBPACK_IMPORTED_MODULE_2__["ɵNgNoValidate"], _angular_forms__WEBPACK_IMPORTED_MODULE_2__.DefaultValueAccessor, _angular_forms__WEBPACK_IMPORTED_MODULE_2__.NgControlStatus, _angular_forms__WEBPACK_IMPORTED_MODULE_2__.NgControlStatusGroup, _angular_forms__WEBPACK_IMPORTED_MODULE_2__.FormGroupDirective, _angular_forms__WEBPACK_IMPORTED_MODULE_2__.FormControlName],
      styles: [".team-form[_ngcontent-%COMP%] {\n  width: 100%;\n}\n\n.form-group[_ngcontent-%COMP%] {\n  margin-bottom: 20px;\n}\n\n.form-group[_ngcontent-%COMP%]   label[_ngcontent-%COMP%] {\n  display: block;\n  margin-bottom: 8px;\n  font-weight: 600;\n  color: #2c3e50;\n}\n\n.form-control[_ngcontent-%COMP%] {\n  width: 100%;\n  padding: 12px;\n  border: 2px solid #ddd;\n  border-radius: 6px;\n  font-size: 16px;\n  transition: border-color 0.3s ease;\n}\n\n.form-control[_ngcontent-%COMP%]:focus {\n  outline: none;\n  border-color: #3498db;\n  box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.1);\n}\n\n.form-control.invalid[_ngcontent-%COMP%] {\n  border-color: #e74c3c;\n}\n\n.error-message[_ngcontent-%COMP%] {\n  color: #e74c3c;\n  font-size: 14px;\n  margin-top: 8px;\n  display: block;\n}\n\n.btn[_ngcontent-%COMP%] {\n  padding: 12px 24px;\n  border: none;\n  border-radius: 6px;\n  font-size: 16px;\n  font-weight: 600;\n  cursor: pointer;\n  transition: all 0.3s ease;\n  display: inline-block;\n  text-decoration: none;\n}\n\n.btn[_ngcontent-%COMP%]:disabled {\n  opacity: 0.6;\n  cursor: not-allowed;\n}\n\n.btn-primary[_ngcontent-%COMP%] {\n  background-color: #3498db;\n  color: white;\n}\n\n.btn-primary[_ngcontent-%COMP%]:hover:not(:disabled) {\n  background-color: #2980b9;\n  transform: translateY(-1px);\n}\n\n.btn-secondary[_ngcontent-%COMP%] {\n  background-color: #95a5a6;\n  color: white;\n  margin-left: 10px;\n}\n\n.btn-secondary[_ngcontent-%COMP%]:hover {\n  background-color: #7f8c8d;\n}\n\n/*# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbIndlYnBhY2s6Ly8uL3NyYy9hcHAvY29tcG9uZW50cy90ZWFtLWZvcm0vdGVhbS1mb3JtLmNvbXBvbmVudC5jc3MiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7RUFDRSxXQUFXO0FBQ2I7O0FBRUE7RUFDRSxtQkFBbUI7QUFDckI7O0FBRUE7RUFDRSxjQUFjO0VBQ2Qsa0JBQWtCO0VBQ2xCLGdCQUFnQjtFQUNoQixjQUFjO0FBQ2hCOztBQUVBO0VBQ0UsV0FBVztFQUNYLGFBQWE7RUFDYixzQkFBc0I7RUFDdEIsa0JBQWtCO0VBQ2xCLGVBQWU7RUFDZixrQ0FBa0M7QUFDcEM7O0FBRUE7RUFDRSxhQUFhO0VBQ2IscUJBQXFCO0VBQ3JCLDZDQUE2QztBQUMvQzs7QUFFQTtFQUNFLHFCQUFxQjtBQUN2Qjs7QUFFQTtFQUNFLGNBQWM7RUFDZCxlQUFlO0VBQ2YsZUFBZTtFQUNmLGNBQWM7QUFDaEI7O0FBRUE7RUFDRSxrQkFBa0I7RUFDbEIsWUFBWTtFQUNaLGtCQUFrQjtFQUNsQixlQUFlO0VBQ2YsZ0JBQWdCO0VBQ2hCLGVBQWU7RUFDZix5QkFBeUI7RUFDekIscUJBQXFCO0VBQ3JCLHFCQUFxQjtBQUN2Qjs7QUFFQTtFQUNFLFlBQVk7RUFDWixtQkFBbUI7QUFDckI7O0FBRUE7RUFDRSx5QkFBeUI7RUFDekIsWUFBWTtBQUNkOztBQUVBO0VBQ0UseUJBQXlCO0VBQ3pCLDJCQUEyQjtBQUM3Qjs7QUFFQTtFQUNFLHlCQUF5QjtFQUN6QixZQUFZO0VBQ1osaUJBQWlCO0FBQ25COztBQUVBO0VBQ0UseUJBQXlCO0FBQzNCIiwic291cmNlc0NvbnRlbnQiOlsiLnRlYW0tZm9ybSB7XG4gIHdpZHRoOiAxMDAlO1xufVxuXG4uZm9ybS1ncm91cCB7XG4gIG1hcmdpbi1ib3R0b206IDIwcHg7XG59XG5cbi5mb3JtLWdyb3VwIGxhYmVsIHtcbiAgZGlzcGxheTogYmxvY2s7XG4gIG1hcmdpbi1ib3R0b206IDhweDtcbiAgZm9udC13ZWlnaHQ6IDYwMDtcbiAgY29sb3I6ICMyYzNlNTA7XG59XG5cbi5mb3JtLWNvbnRyb2wge1xuICB3aWR0aDogMTAwJTtcbiAgcGFkZGluZzogMTJweDtcbiAgYm9yZGVyOiAycHggc29saWQgI2RkZDtcbiAgYm9yZGVyLXJhZGl1czogNnB4O1xuICBmb250LXNpemU6IDE2cHg7XG4gIHRyYW5zaXRpb246IGJvcmRlci1jb2xvciAwLjNzIGVhc2U7XG59XG5cbi5mb3JtLWNvbnRyb2w6Zm9jdXMge1xuICBvdXRsaW5lOiBub25lO1xuICBib3JkZXItY29sb3I6ICMzNDk4ZGI7XG4gIGJveC1zaGFkb3c6IDAgMCAwIDNweCByZ2JhKDUyLCAxNTIsIDIxOSwgMC4xKTtcbn1cblxuLmZvcm0tY29udHJvbC5pbnZhbGlkIHtcbiAgYm9yZGVyLWNvbG9yOiAjZTc0YzNjO1xufVxuXG4uZXJyb3ItbWVzc2FnZSB7XG4gIGNvbG9yOiAjZTc0YzNjO1xuICBmb250LXNpemU6IDE0cHg7XG4gIG1hcmdpbi10b3A6IDhweDtcbiAgZGlzcGxheTogYmxvY2s7XG59XG5cbi5idG4ge1xuICBwYWRkaW5nOiAxMnB4IDI0cHg7XG4gIGJvcmRlcjogbm9uZTtcbiAgYm9yZGVyLXJhZGl1czogNnB4O1xuICBmb250LXNpemU6IDE2cHg7XG4gIGZvbnQtd2VpZ2h0OiA2MDA7XG4gIGN1cnNvcjogcG9pbnRlcjtcbiAgdHJhbnNpdGlvbjogYWxsIDAuM3MgZWFzZTtcbiAgZGlzcGxheTogaW5saW5lLWJsb2NrO1xuICB0ZXh0LWRlY29yYXRpb246IG5vbmU7XG59XG5cbi5idG46ZGlzYWJsZWQge1xuICBvcGFjaXR5OiAwLjY7XG4gIGN1cnNvcjogbm90LWFsbG93ZWQ7XG59XG5cbi5idG4tcHJpbWFyeSB7XG4gIGJhY2tncm91bmQtY29sb3I6ICMzNDk4ZGI7XG4gIGNvbG9yOiB3aGl0ZTtcbn1cblxuLmJ0bi1wcmltYXJ5OmhvdmVyOm5vdCg6ZGlzYWJsZWQpIHtcbiAgYmFja2dyb3VuZC1jb2xvcjogIzI5ODBiOTtcbiAgdHJhbnNmb3JtOiB0cmFuc2xhdGVZKC0xcHgpO1xufVxuXG4uYnRuLXNlY29uZGFyeSB7XG4gIGJhY2tncm91bmQtY29sb3I6ICM5NWE1YTY7XG4gIGNvbG9yOiB3aGl0ZTtcbiAgbWFyZ2luLWxlZnQ6IDEwcHg7XG59XG5cbi5idG4tc2Vjb25kYXJ5OmhvdmVyIHtcbiAgYmFja2dyb3VuZC1jb2xvcjogIzdmOGM4ZDtcbn1cbiJdLCJzb3VyY2VSb290IjoiIn0= */"]
    });
  }
}

/***/ }),

/***/ 5281:
/*!*************************************************************!*\
  !*** ./src/app/components/team-list/team-list.component.ts ***!
  \*************************************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   TeamListComponent: () => (/* binding */ TeamListComponent)
/* harmony export */ });
/* harmony import */ var _angular_core__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @angular/core */ 7580);
/* harmony import */ var _services_teams_service__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../../services/teams.service */ 5092);
/* harmony import */ var _angular_common__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @angular/common */ 316);



function TeamListComponent_div_1_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 6);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1, " Loading teams... ");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
}
function TeamListComponent_div_2_Template(rf, ctx) {
  if (rf & 1) {
    const _r6 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵgetCurrentView"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 7);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](2, "button", 8);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵlistener"]("click", function TeamListComponent_div_2_Template_button_click_2_listener() {
      _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵrestoreView"](_r6);
      const ctx_r5 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]();
      return _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵresetView"](ctx_r5.loadTeams());
    });
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](3, "Retry");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]()();
  }
  if (rf & 2) {
    const ctx_r1 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"](" ", ctx_r1.errorMessage, " ");
  }
}
function TeamListComponent_div_3_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 9)(1, "p");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](2, "No teams created yet. Create your first team above!");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]()();
  }
}
function TeamListComponent_div_4_div_1_span_15_ng_container_1_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementContainerStart"](0);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementContainerEnd"]();
  }
  if (rf & 2) {
    const c_r11 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]().ngIf;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate2"](" ", c_r11.failing_policies, " of ", c_r11.total_policies, " policies failing ");
  }
}
function TeamListComponent_div_4_div_1_span_15_ng_container_2_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementContainerStart"](0);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementContainerEnd"]();
  }
  if (rf & 2) {
    const c_r11 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]().ngIf;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"](" ", c_r11.total_policies, " policies passing ");
  }
}
function TeamListComponent_div_4_div_1_span_15_ng_container_3_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementContainerStart"](0);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementContainerEnd"]();
  }
  if (rf & 2) {
    const c_r11 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]().ngIf;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"](" ", c_r11.reason || "Status unavailable", " ");
  }
}
function TeamListComponent_div_4_div_1_span_15_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "span", 25);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](1, TeamListComponent_div_4_div_1_span_15_ng_container_1_Template, 2, 2, "ng-container", 26);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](2, TeamListComponent_div_4_div_1_span_15_ng_container_2_Template, 2, 1, "ng-container", 26);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](3, TeamListComponent_div_4_div_1_span_15_ng_container_3_Template, 2, 1, "ng-container", 26);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const c_r11 = ctx.ngIf;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("title", c_r11.reason || "");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", c_r11.status === "non_compliant");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", c_r11.status === "compliant");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", c_r11.status === "unknown");
  }
}
function TeamListComponent_div_4_div_1_div_18_div_1_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 29);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1, " Checking policies\u2026 ");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
}
function TeamListComponent_div_4_div_1_div_18_ng_container_2_p_1_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "p", 32);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const detail_r20 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]().ngIf;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"](" ", detail_r20.reason || "No platform policies are enforced yet \u2014 nothing to evaluate.", " ");
  }
}
function TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_li_1_span_8_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "span", 42);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const policy_r25 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]().$implicit;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"](" ", policy_r25.violation_count, " ");
  }
}
function TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_li_1_ul_9_li_1_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "li");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const msg_r30 = ctx.$implicit;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate"](msg_r30);
  }
}
function TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_li_1_ul_9_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "ul", 43);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](1, TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_li_1_ul_9_li_1_Template, 2, 1, "li", 44);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const policy_r25 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]().$implicit;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngForOf", policy_r25.messages);
  }
}
function TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_li_1_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "li", 35)(1, "div", 36)(2, "span", 37);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](3);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](4, "span", 38);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](5);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](6, "span", 39);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](7);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](8, TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_li_1_span_8_Template, 2, 1, "span", 40);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](9, TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_li_1_ul_9_Template, 2, 1, "ul", 41);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const policy_r25 = ctx.$implicit;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngClass", policy_r25.compliant ? "policy-ok" : "policy-fail");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](3);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate"](policy_r25.compliant ? "\u2713" : "\u2717");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate"](policy_r25.name);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate"](policy_r25.kind);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", !policy_r25.compliant);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", policy_r25.messages.length > 0);
  }
}
function TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "ul", 33);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](1, TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_li_1_Template, 10, 6, "li", 34);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const detail_r20 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]().ngIf;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngForOf", detail_r20.policies);
  }
}
function TeamListComponent_div_4_div_1_div_18_ng_container_2_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementContainerStart"](0);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](1, TeamListComponent_div_4_div_1_div_18_ng_container_2_p_1_Template, 2, 1, "p", 30);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](2, TeamListComponent_div_4_div_1_div_18_ng_container_2_ul_2_Template, 2, 1, "ul", 31);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementContainerEnd"]();
  }
  if (rf & 2) {
    const detail_r20 = ctx.ngIf;
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", detail_r20.policies.length === 0);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", detail_r20.policies.length > 0);
  }
}
function TeamListComponent_div_4_div_1_div_18_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 27);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](1, TeamListComponent_div_4_div_1_div_18_div_1_Template, 2, 0, "div", 28);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](2, TeamListComponent_div_4_div_1_div_18_ng_container_2_Template, 3, 2, "ng-container", 26);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const team_r8 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]().$implicit;
    const ctx_r10 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx_r10.loadingDetail[team_r8.id]);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx_r10.complianceDetail[team_r8.id]);
  }
}
function TeamListComponent_div_4_div_1_Template(rf, ctx) {
  if (rf & 1) {
    const _r35 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵgetCurrentView"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 12)(1, "div", 13)(2, "h3", 14);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](3);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](4, "button", 15);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵlistener"]("click", function TeamListComponent_div_4_div_1_Template_button_click_4_listener() {
      const restoredCtx = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵrestoreView"](_r35);
      const team_r8 = restoredCtx.$implicit;
      const ctx_r34 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"](2);
      return _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵresetView"](ctx_r34.deleteTeam(team_r8.id, team_r8.name));
    });
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](5, " Delete ");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]()();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](6, "div", 16)(7, "p", 17);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](8);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](9, "p", 18);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](10);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]()();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](11, "div", 19)(12, "button", 20);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵlistener"]("click", function TeamListComponent_div_4_div_1_Template_button_click_12_listener() {
      const restoredCtx = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵrestoreView"](_r35);
      const team_r8 = restoredCtx.$implicit;
      const ctx_r36 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"](2);
      return _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵresetView"](ctx_r36.toggleDetail(team_r8.id));
    });
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](13, "span", 21);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](14);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](15, TeamListComponent_div_4_div_1_span_15_Template, 4, 4, "span", 22);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](16, "span", 23);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](17);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]()();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](18, TeamListComponent_div_4_div_1_div_18_Template, 3, 2, "div", 24);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]()();
  }
  if (rf & 2) {
    const team_r8 = ctx.$implicit;
    const ctx_r7 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](3);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate"](team_r8.name);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](5);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"]("ID: ", team_r8.id, "");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"]("Created: ", ctx_r7.formatDate(team_r8.created_at), "");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵattribute"]("aria-expanded", ctx_r7.expanded[team_r8.id]);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngClass", "badge-" + ctx_r7.statusOf(team_r8.id));
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"](" ", ctx_r7.statusLabel(team_r8.id), " ");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx_r7.compliance[team_r8.id]);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](2);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate"](ctx_r7.expanded[team_r8.id] ? "\u25B2" : "\u25BC");
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx_r7.expanded[team_r8.id]);
  }
}
function TeamListComponent_div_4_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 10);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](1, TeamListComponent_div_4_div_1_Template, 19, 9, "div", 11);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const ctx_r3 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngForOf", ctx_r3.teams);
  }
}
function TeamListComponent_div_5_Template(rf, ctx) {
  if (rf & 1) {
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 45);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtext"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
  }
  if (rf & 2) {
    const ctx_r4 = _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵnextContext"]();
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
    _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtextInterpolate1"](" Total teams: ", ctx_r4.teams.length, " ");
  }
}
class TeamListComponent {
  constructor(teamsService) {
    this.teamsService = teamsService;
    this.teams = [];
    this.isLoading = true;
    this.errorMessage = "";
    // Compliance state, keyed by team id.
    this.compliance = {};
    this.complianceDetail = {};
    this.expanded = {};
    this.loadingDetail = {};
  }
  ngOnInit() {
    this.loadTeams();
  }
  loadTeams() {
    this.isLoading = true;
    this.errorMessage = "";
    this.teamsService.getTeams().subscribe({
      next: teams => {
        this.teams = teams;
        this.isLoading = false;
        this.loadCompliance();
      },
      error: error => {
        this.errorMessage = error;
        this.isLoading = false;
      }
    });
  }
  loadCompliance() {
    this.teamsService.getComplianceSummaries().subscribe({
      next: summaries => {
        this.compliance = {};
        for (const summary of summaries) {
          this.compliance[summary.team_id] = summary;
        }
      },
      // Compliance is supplementary; a failure here must not blank the team list.
      error: error => console.error("Failed to load compliance:", error)
    });
  }
  toggleDetail(teamId) {
    this.expanded[teamId] = !this.expanded[teamId];
    if (this.expanded[teamId] && !this.complianceDetail[teamId]) {
      this.loadingDetail[teamId] = true;
      this.teamsService.getTeamCompliance(teamId).subscribe({
        next: detail => {
          this.complianceDetail[teamId] = detail;
          this.loadingDetail[teamId] = false;
        },
        error: error => {
          console.error("Failed to load compliance detail:", error);
          this.loadingDetail[teamId] = false;
        }
      });
    }
  }
  statusOf(teamId) {
    return this.compliance[teamId]?.status ?? "unknown";
  }
  statusLabel(teamId) {
    switch (this.statusOf(teamId)) {
      case "compliant":
        return "Compliant";
      case "non_compliant":
        return "Non-compliant";
      default:
        return "Unknown";
    }
  }
  deleteTeam(teamId, teamName) {
    if (confirm(`Are you sure you want to delete team "${teamName}"?`)) {
      this.teamsService.deleteTeam(teamId).subscribe({
        next: () => {
          this.loadTeams();
        },
        error: error => {
          this.errorMessage = error;
        }
      });
    }
  }
  formatDate(dateString) {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  }
  static {
    this.ɵfac = function TeamListComponent_Factory(t) {
      return new (t || TeamListComponent)(_angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵdirectiveInject"](_services_teams_service__WEBPACK_IMPORTED_MODULE_0__.TeamsService));
    };
  }
  static {
    this.ɵcmp = /*@__PURE__*/_angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵdefineComponent"]({
      type: TeamListComponent,
      selectors: [["app-team-list"]],
      decls: 6,
      vars: 5,
      consts: [[1, "team-list"], ["class", "loading", 4, "ngIf"], ["class", "error-message", 4, "ngIf"], ["class", "empty-state", 4, "ngIf"], ["class", "teams-grid", 4, "ngIf"], ["class", "teams-count", 4, "ngIf"], [1, "loading"], [1, "error-message"], [1, "btn", "btn-secondary", 3, "click"], [1, "empty-state"], [1, "teams-grid"], ["class", "team-card", 4, "ngFor", "ngForOf"], [1, "team-card"], [1, "team-header"], [1, "team-name"], ["title", "Delete team", 1, "btn", "btn-danger", "btn-sm", 3, "click"], [1, "team-details"], [1, "team-id"], [1, "team-created"], [1, "compliance"], [1, "compliance-toggle", 3, "click"], [1, "badge", 3, "ngClass"], ["class", "policy-count", 3, "title", 4, "ngIf"], [1, "chevron"], ["class", "compliance-detail", 4, "ngIf"], [1, "policy-count", 3, "title"], [4, "ngIf"], [1, "compliance-detail"], ["class", "detail-loading", 4, "ngIf"], [1, "detail-loading"], ["class", "detail-empty", 4, "ngIf"], ["class", "policy-list", 4, "ngIf"], [1, "detail-empty"], [1, "policy-list"], ["class", "policy", 3, "ngClass", 4, "ngFor", "ngForOf"], [1, "policy", 3, "ngClass"], [1, "policy-head"], [1, "policy-mark"], [1, "policy-name"], [1, "policy-kind"], ["class", "policy-vcount", 4, "ngIf"], ["class", "policy-messages", 4, "ngIf"], [1, "policy-vcount"], [1, "policy-messages"], [4, "ngFor", "ngForOf"], [1, "teams-count"]],
      template: function TeamListComponent_Template(rf, ctx) {
        if (rf & 1) {
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementStart"](0, "div", 0);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](1, TeamListComponent_div_1_Template, 2, 0, "div", 1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](2, TeamListComponent_div_2_Template, 4, 1, "div", 2);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](3, TeamListComponent_div_3_Template, 3, 0, "div", 3);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](4, TeamListComponent_div_4_Template, 2, 1, "div", 4);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵtemplate"](5, TeamListComponent_div_5_Template, 2, 1, "div", 5);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵelementEnd"]();
        }
        if (rf & 2) {
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx.isLoading);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", ctx.errorMessage && !ctx.isLoading);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", !ctx.isLoading && !ctx.errorMessage && ctx.teams.length === 0);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", !ctx.isLoading && !ctx.errorMessage && ctx.teams.length > 0);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵadvance"](1);
          _angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵproperty"]("ngIf", !ctx.isLoading && ctx.teams.length > 0);
        }
      },
      dependencies: [_angular_common__WEBPACK_IMPORTED_MODULE_2__.NgClass, _angular_common__WEBPACK_IMPORTED_MODULE_2__.NgForOf, _angular_common__WEBPACK_IMPORTED_MODULE_2__.NgIf],
      styles: ["\n\n.team-list[_ngcontent-%COMP%] {\n  width: 100%;\n}\n\n.loading[_ngcontent-%COMP%] {\n  text-align: center;\n  padding: 40px;\n  color: #7f8c8d;\n  font-size: 18px;\n}\n\n.empty-state[_ngcontent-%COMP%] {\n  text-align: center;\n  padding: 40px;\n  color: #7f8c8d;\n}\n\n.empty-state[_ngcontent-%COMP%]   p[_ngcontent-%COMP%] {\n  font-size: 16px;\n}\n\n.teams-grid[_ngcontent-%COMP%] {\n  display: grid;\n  gap: 20px;\n  margin-bottom: 20px;\n}\n\n.team-card[_ngcontent-%COMP%] {\n  border: 2px solid #ecf0f1;\n  border-radius: 8px;\n  padding: 20px;\n  transition: all 0.3s ease;\n  background: #fafafa;\n}\n\n.team-card[_ngcontent-%COMP%]:hover {\n  border-color: #3498db;\n  transform: translateY(-2px);\n  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);\n}\n\n.team-header[_ngcontent-%COMP%] {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-bottom: 15px;\n}\n\n.team-name[_ngcontent-%COMP%] {\n  color: #2c3e50;\n  margin: 0;\n  font-size: 1.3rem;\n}\n\n.team-details[_ngcontent-%COMP%]   p[_ngcontent-%COMP%] {\n  margin: 5px 0;\n  color: #7f8c8d;\n  font-size: 14px;\n}\n\n.team-id[_ngcontent-%COMP%] {\n  font-family: 'Courier New', monospace;\n  word-break: break-all;\n}\n\n.team-created[_ngcontent-%COMP%] {\n  font-weight: 500;\n}\n\n.btn-danger[_ngcontent-%COMP%] {\n  background-color: #e74c3c;\n  color: white;\n}\n\n.btn-danger[_ngcontent-%COMP%]:hover {\n  background-color: #c0392b;\n}\n\n.btn-sm[_ngcontent-%COMP%] {\n  padding: 8px 16px;\n  font-size: 14px;\n}\n\n.teams-count[_ngcontent-%COMP%] {\n  text-align: center;\n  padding: 15px;\n  background: #ecf0f1;\n  border-radius: 6px;\n  color: #7f8c8d;\n  font-weight: 600;\n}\n\n\n\n.compliance[_ngcontent-%COMP%] {\n  margin-top: 15px;\n  border-top: 1px solid #ecf0f1;\n  padding-top: 12px;\n}\n\n.compliance-toggle[_ngcontent-%COMP%] {\n  display: flex;\n  align-items: center;\n  gap: 10px;\n  width: 100%;\n  background: none;\n  border: none;\n  padding: 0;\n  cursor: pointer;\n  text-align: left;\n  font: inherit;\n}\n\n.badge[_ngcontent-%COMP%] {\n  display: inline-block;\n  padding: 3px 10px;\n  border-radius: 12px;\n  font-size: 12px;\n  font-weight: 700;\n  text-transform: uppercase;\n  letter-spacing: 0.03em;\n  color: #fff;\n  white-space: nowrap;\n}\n\n.badge-compliant[_ngcontent-%COMP%] {\n  background-color: #27ae60;\n}\n\n.badge-non_compliant[_ngcontent-%COMP%] {\n  background-color: #e74c3c;\n}\n\n.badge-unknown[_ngcontent-%COMP%] {\n  background-color: #95a5a6;\n}\n\n.policy-count[_ngcontent-%COMP%] {\n  flex: 1;\n  color: #7f8c8d;\n  font-size: 13px;\n}\n\n.chevron[_ngcontent-%COMP%] {\n  color: #b0b8bd;\n  font-size: 11px;\n}\n\n.compliance-detail[_ngcontent-%COMP%] {\n  margin-top: 12px;\n}\n\n.detail-loading[_ngcontent-%COMP%], .detail-empty[_ngcontent-%COMP%] {\n  color: #7f8c8d;\n  font-size: 13px;\n  font-style: italic;\n  margin: 6px 0;\n}\n\n.policy-list[_ngcontent-%COMP%] {\n  list-style: none;\n  margin: 0;\n  padding: 0;\n  display: flex;\n  flex-direction: column;\n  gap: 6px;\n}\n\n.policy[_ngcontent-%COMP%] {\n  border-radius: 6px;\n  padding: 8px 10px;\n  background: #fff;\n  border: 1px solid #ecf0f1;\n}\n\n.policy-fail[_ngcontent-%COMP%] {\n  border-color: #f5b7b1;\n  background: #fdf2f1;\n}\n\n.policy-head[_ngcontent-%COMP%] {\n  display: flex;\n  align-items: center;\n  gap: 8px;\n}\n\n.policy-mark[_ngcontent-%COMP%] {\n  font-weight: 700;\n}\n\n.policy-ok[_ngcontent-%COMP%]   .policy-mark[_ngcontent-%COMP%] {\n  color: #27ae60;\n}\n\n.policy-fail[_ngcontent-%COMP%]   .policy-mark[_ngcontent-%COMP%] {\n  color: #e74c3c;\n}\n\n.policy-name[_ngcontent-%COMP%] {\n  font-weight: 600;\n  color: #2c3e50;\n  font-size: 14px;\n}\n\n.policy-kind[_ngcontent-%COMP%] {\n  color: #95a5a6;\n  font-size: 12px;\n  font-family: \"Courier New\", monospace;\n}\n\n.policy-vcount[_ngcontent-%COMP%] {\n  margin-left: auto;\n  background: #e74c3c;\n  color: #fff;\n  border-radius: 10px;\n  padding: 1px 8px;\n  font-size: 12px;\n  font-weight: 700;\n}\n\n.policy-messages[_ngcontent-%COMP%] {\n  list-style: disc;\n  margin: 6px 0 0;\n  padding-left: 26px;\n  color: #7f8c8d;\n  font-size: 12px;\n}\n\n.policy-messages[_ngcontent-%COMP%]   li[_ngcontent-%COMP%] {\n  margin: 2px 0;\n  word-break: break-word;\n}\n\n/*# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbIndlYnBhY2s6Ly8uL3NyYy9hcHAvY29tcG9uZW50cy90ZWFtLWxpc3QvdGVhbS1saXN0LmNvbXBvbmVudC5jc3MiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUEseURBQXlEO0FBQ3pEO0VBQ0UsV0FBVztBQUNiOztBQUVBO0VBQ0Usa0JBQWtCO0VBQ2xCLGFBQWE7RUFDYixjQUFjO0VBQ2QsZUFBZTtBQUNqQjs7QUFFQTtFQUNFLGtCQUFrQjtFQUNsQixhQUFhO0VBQ2IsY0FBYztBQUNoQjs7QUFFQTtFQUNFLGVBQWU7QUFDakI7O0FBRUE7RUFDRSxhQUFhO0VBQ2IsU0FBUztFQUNULG1CQUFtQjtBQUNyQjs7QUFFQTtFQUNFLHlCQUF5QjtFQUN6QixrQkFBa0I7RUFDbEIsYUFBYTtFQUNiLHlCQUF5QjtFQUN6QixtQkFBbUI7QUFDckI7O0FBRUE7RUFDRSxxQkFBcUI7RUFDckIsMkJBQTJCO0VBQzNCLHdDQUF3QztBQUMxQzs7QUFFQTtFQUNFLGFBQWE7RUFDYiw4QkFBOEI7RUFDOUIsbUJBQW1CO0VBQ25CLG1CQUFtQjtBQUNyQjs7QUFFQTtFQUNFLGNBQWM7RUFDZCxTQUFTO0VBQ1QsaUJBQWlCO0FBQ25COztBQUVBO0VBQ0UsYUFBYTtFQUNiLGNBQWM7RUFDZCxlQUFlO0FBQ2pCOztBQUVBO0VBQ0UscUNBQXFDO0VBQ3JDLHFCQUFxQjtBQUN2Qjs7QUFFQTtFQUNFLGdCQUFnQjtBQUNsQjs7QUFFQTtFQUNFLHlCQUF5QjtFQUN6QixZQUFZO0FBQ2Q7O0FBRUE7RUFDRSx5QkFBeUI7QUFDM0I7O0FBRUE7RUFDRSxpQkFBaUI7RUFDakIsZUFBZTtBQUNqQjs7QUFFQTtFQUNFLGtCQUFrQjtFQUNsQixhQUFhO0VBQ2IsbUJBQW1CO0VBQ25CLGtCQUFrQjtFQUNsQixjQUFjO0VBQ2QsZ0JBQWdCO0FBQ2xCOztBQUVBLHVCQUF1QjtBQUN2QjtFQUNFLGdCQUFnQjtFQUNoQiw2QkFBNkI7RUFDN0IsaUJBQWlCO0FBQ25COztBQUVBO0VBQ0UsYUFBYTtFQUNiLG1CQUFtQjtFQUNuQixTQUFTO0VBQ1QsV0FBVztFQUNYLGdCQUFnQjtFQUNoQixZQUFZO0VBQ1osVUFBVTtFQUNWLGVBQWU7RUFDZixnQkFBZ0I7RUFDaEIsYUFBYTtBQUNmOztBQUVBO0VBQ0UscUJBQXFCO0VBQ3JCLGlCQUFpQjtFQUNqQixtQkFBbUI7RUFDbkIsZUFBZTtFQUNmLGdCQUFnQjtFQUNoQix5QkFBeUI7RUFDekIsc0JBQXNCO0VBQ3RCLFdBQVc7RUFDWCxtQkFBbUI7QUFDckI7O0FBRUE7RUFDRSx5QkFBeUI7QUFDM0I7O0FBRUE7RUFDRSx5QkFBeUI7QUFDM0I7O0FBRUE7RUFDRSx5QkFBeUI7QUFDM0I7O0FBRUE7RUFDRSxPQUFPO0VBQ1AsY0FBYztFQUNkLGVBQWU7QUFDakI7O0FBRUE7RUFDRSxjQUFjO0VBQ2QsZUFBZTtBQUNqQjs7QUFFQTtFQUNFLGdCQUFnQjtBQUNsQjs7QUFFQTs7RUFFRSxjQUFjO0VBQ2QsZUFBZTtFQUNmLGtCQUFrQjtFQUNsQixhQUFhO0FBQ2Y7O0FBRUE7RUFDRSxnQkFBZ0I7RUFDaEIsU0FBUztFQUNULFVBQVU7RUFDVixhQUFhO0VBQ2Isc0JBQXNCO0VBQ3RCLFFBQVE7QUFDVjs7QUFFQTtFQUNFLGtCQUFrQjtFQUNsQixpQkFBaUI7RUFDakIsZ0JBQWdCO0VBQ2hCLHlCQUF5QjtBQUMzQjs7QUFFQTtFQUNFLHFCQUFxQjtFQUNyQixtQkFBbUI7QUFDckI7O0FBRUE7RUFDRSxhQUFhO0VBQ2IsbUJBQW1CO0VBQ25CLFFBQVE7QUFDVjs7QUFFQTtFQUNFLGdCQUFnQjtBQUNsQjs7QUFFQTtFQUNFLGNBQWM7QUFDaEI7O0FBRUE7RUFDRSxjQUFjO0FBQ2hCOztBQUVBO0VBQ0UsZ0JBQWdCO0VBQ2hCLGNBQWM7RUFDZCxlQUFlO0FBQ2pCOztBQUVBO0VBQ0UsY0FBYztFQUNkLGVBQWU7RUFDZixxQ0FBcUM7QUFDdkM7O0FBRUE7RUFDRSxpQkFBaUI7RUFDakIsbUJBQW1CO0VBQ25CLFdBQVc7RUFDWCxtQkFBbUI7RUFDbkIsZ0JBQWdCO0VBQ2hCLGVBQWU7RUFDZixnQkFBZ0I7QUFDbEI7O0FBRUE7RUFDRSxnQkFBZ0I7RUFDaEIsZUFBZTtFQUNmLGtCQUFrQjtFQUNsQixjQUFjO0VBQ2QsZUFBZTtBQUNqQjs7QUFFQTtFQUNFLGFBQWE7RUFDYixzQkFBc0I7QUFDeEIiLCJzb3VyY2VzQ29udGVudCI6WyIvKiBzcmMvYXBwL2NvbXBvbmVudHMvdGVhbS1saXN0L3RlYW0tbGlzdC5jb21wb25lbnQuY3NzICovXG4udGVhbS1saXN0IHtcbiAgd2lkdGg6IDEwMCU7XG59XG5cbi5sb2FkaW5nIHtcbiAgdGV4dC1hbGlnbjogY2VudGVyO1xuICBwYWRkaW5nOiA0MHB4O1xuICBjb2xvcjogIzdmOGM4ZDtcbiAgZm9udC1zaXplOiAxOHB4O1xufVxuXG4uZW1wdHktc3RhdGUge1xuICB0ZXh0LWFsaWduOiBjZW50ZXI7XG4gIHBhZGRpbmc6IDQwcHg7XG4gIGNvbG9yOiAjN2Y4YzhkO1xufVxuXG4uZW1wdHktc3RhdGUgcCB7XG4gIGZvbnQtc2l6ZTogMTZweDtcbn1cblxuLnRlYW1zLWdyaWQge1xuICBkaXNwbGF5OiBncmlkO1xuICBnYXA6IDIwcHg7XG4gIG1hcmdpbi1ib3R0b206IDIwcHg7XG59XG5cbi50ZWFtLWNhcmQge1xuICBib3JkZXI6IDJweCBzb2xpZCAjZWNmMGYxO1xuICBib3JkZXItcmFkaXVzOiA4cHg7XG4gIHBhZGRpbmc6IDIwcHg7XG4gIHRyYW5zaXRpb246IGFsbCAwLjNzIGVhc2U7XG4gIGJhY2tncm91bmQ6ICNmYWZhZmE7XG59XG5cbi50ZWFtLWNhcmQ6aG92ZXIge1xuICBib3JkZXItY29sb3I6ICMzNDk4ZGI7XG4gIHRyYW5zZm9ybTogdHJhbnNsYXRlWSgtMnB4KTtcbiAgYm94LXNoYWRvdzogMCA0cHggOHB4IHJnYmEoMCwgMCwgMCwgMC4xKTtcbn1cblxuLnRlYW0taGVhZGVyIHtcbiAgZGlzcGxheTogZmxleDtcbiAganVzdGlmeS1jb250ZW50OiBzcGFjZS1iZXR3ZWVuO1xuICBhbGlnbi1pdGVtczogY2VudGVyO1xuICBtYXJnaW4tYm90dG9tOiAxNXB4O1xufVxuXG4udGVhbS1uYW1lIHtcbiAgY29sb3I6ICMyYzNlNTA7XG4gIG1hcmdpbjogMDtcbiAgZm9udC1zaXplOiAxLjNyZW07XG59XG5cbi50ZWFtLWRldGFpbHMgcCB7XG4gIG1hcmdpbjogNXB4IDA7XG4gIGNvbG9yOiAjN2Y4YzhkO1xuICBmb250LXNpemU6IDE0cHg7XG59XG5cbi50ZWFtLWlkIHtcbiAgZm9udC1mYW1pbHk6ICdDb3VyaWVyIE5ldycsIG1vbm9zcGFjZTtcbiAgd29yZC1icmVhazogYnJlYWstYWxsO1xufVxuXG4udGVhbS1jcmVhdGVkIHtcbiAgZm9udC13ZWlnaHQ6IDUwMDtcbn1cblxuLmJ0bi1kYW5nZXIge1xuICBiYWNrZ3JvdW5kLWNvbG9yOiAjZTc0YzNjO1xuICBjb2xvcjogd2hpdGU7XG59XG5cbi5idG4tZGFuZ2VyOmhvdmVyIHtcbiAgYmFja2dyb3VuZC1jb2xvcjogI2MwMzkyYjtcbn1cblxuLmJ0bi1zbSB7XG4gIHBhZGRpbmc6IDhweCAxNnB4O1xuICBmb250LXNpemU6IDE0cHg7XG59XG5cbi50ZWFtcy1jb3VudCB7XG4gIHRleHQtYWxpZ246IGNlbnRlcjtcbiAgcGFkZGluZzogMTVweDtcbiAgYmFja2dyb3VuZDogI2VjZjBmMTtcbiAgYm9yZGVyLXJhZGl1czogNnB4O1xuICBjb2xvcjogIzdmOGM4ZDtcbiAgZm9udC13ZWlnaHQ6IDYwMDtcbn1cblxuLyogLS0tIENvbXBsaWFuY2UgLS0tICovXG4uY29tcGxpYW5jZSB7XG4gIG1hcmdpbi10b3A6IDE1cHg7XG4gIGJvcmRlci10b3A6IDFweCBzb2xpZCAjZWNmMGYxO1xuICBwYWRkaW5nLXRvcDogMTJweDtcbn1cblxuLmNvbXBsaWFuY2UtdG9nZ2xlIHtcbiAgZGlzcGxheTogZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAgZ2FwOiAxMHB4O1xuICB3aWR0aDogMTAwJTtcbiAgYmFja2dyb3VuZDogbm9uZTtcbiAgYm9yZGVyOiBub25lO1xuICBwYWRkaW5nOiAwO1xuICBjdXJzb3I6IHBvaW50ZXI7XG4gIHRleHQtYWxpZ246IGxlZnQ7XG4gIGZvbnQ6IGluaGVyaXQ7XG59XG5cbi5iYWRnZSB7XG4gIGRpc3BsYXk6IGlubGluZS1ibG9jaztcbiAgcGFkZGluZzogM3B4IDEwcHg7XG4gIGJvcmRlci1yYWRpdXM6IDEycHg7XG4gIGZvbnQtc2l6ZTogMTJweDtcbiAgZm9udC13ZWlnaHQ6IDcwMDtcbiAgdGV4dC10cmFuc2Zvcm06IHVwcGVyY2FzZTtcbiAgbGV0dGVyLXNwYWNpbmc6IDAuMDNlbTtcbiAgY29sb3I6ICNmZmY7XG4gIHdoaXRlLXNwYWNlOiBub3dyYXA7XG59XG5cbi5iYWRnZS1jb21wbGlhbnQge1xuICBiYWNrZ3JvdW5kLWNvbG9yOiAjMjdhZTYwO1xufVxuXG4uYmFkZ2Utbm9uX2NvbXBsaWFudCB7XG4gIGJhY2tncm91bmQtY29sb3I6ICNlNzRjM2M7XG59XG5cbi5iYWRnZS11bmtub3duIHtcbiAgYmFja2dyb3VuZC1jb2xvcjogIzk1YTVhNjtcbn1cblxuLnBvbGljeS1jb3VudCB7XG4gIGZsZXg6IDE7XG4gIGNvbG9yOiAjN2Y4YzhkO1xuICBmb250LXNpemU6IDEzcHg7XG59XG5cbi5jaGV2cm9uIHtcbiAgY29sb3I6ICNiMGI4YmQ7XG4gIGZvbnQtc2l6ZTogMTFweDtcbn1cblxuLmNvbXBsaWFuY2UtZGV0YWlsIHtcbiAgbWFyZ2luLXRvcDogMTJweDtcbn1cblxuLmRldGFpbC1sb2FkaW5nLFxuLmRldGFpbC1lbXB0eSB7XG4gIGNvbG9yOiAjN2Y4YzhkO1xuICBmb250LXNpemU6IDEzcHg7XG4gIGZvbnQtc3R5bGU6IGl0YWxpYztcbiAgbWFyZ2luOiA2cHggMDtcbn1cblxuLnBvbGljeS1saXN0IHtcbiAgbGlzdC1zdHlsZTogbm9uZTtcbiAgbWFyZ2luOiAwO1xuICBwYWRkaW5nOiAwO1xuICBkaXNwbGF5OiBmbGV4O1xuICBmbGV4LWRpcmVjdGlvbjogY29sdW1uO1xuICBnYXA6IDZweDtcbn1cblxuLnBvbGljeSB7XG4gIGJvcmRlci1yYWRpdXM6IDZweDtcbiAgcGFkZGluZzogOHB4IDEwcHg7XG4gIGJhY2tncm91bmQ6ICNmZmY7XG4gIGJvcmRlcjogMXB4IHNvbGlkICNlY2YwZjE7XG59XG5cbi5wb2xpY3ktZmFpbCB7XG4gIGJvcmRlci1jb2xvcjogI2Y1YjdiMTtcbiAgYmFja2dyb3VuZDogI2ZkZjJmMTtcbn1cblxuLnBvbGljeS1oZWFkIHtcbiAgZGlzcGxheTogZmxleDtcbiAgYWxpZ24taXRlbXM6IGNlbnRlcjtcbiAgZ2FwOiA4cHg7XG59XG5cbi5wb2xpY3ktbWFyayB7XG4gIGZvbnQtd2VpZ2h0OiA3MDA7XG59XG5cbi5wb2xpY3ktb2sgLnBvbGljeS1tYXJrIHtcbiAgY29sb3I6ICMyN2FlNjA7XG59XG5cbi5wb2xpY3ktZmFpbCAucG9saWN5LW1hcmsge1xuICBjb2xvcjogI2U3NGMzYztcbn1cblxuLnBvbGljeS1uYW1lIHtcbiAgZm9udC13ZWlnaHQ6IDYwMDtcbiAgY29sb3I6ICMyYzNlNTA7XG4gIGZvbnQtc2l6ZTogMTRweDtcbn1cblxuLnBvbGljeS1raW5kIHtcbiAgY29sb3I6ICM5NWE1YTY7XG4gIGZvbnQtc2l6ZTogMTJweDtcbiAgZm9udC1mYW1pbHk6IFwiQ291cmllciBOZXdcIiwgbW9ub3NwYWNlO1xufVxuXG4ucG9saWN5LXZjb3VudCB7XG4gIG1hcmdpbi1sZWZ0OiBhdXRvO1xuICBiYWNrZ3JvdW5kOiAjZTc0YzNjO1xuICBjb2xvcjogI2ZmZjtcbiAgYm9yZGVyLXJhZGl1czogMTBweDtcbiAgcGFkZGluZzogMXB4IDhweDtcbiAgZm9udC1zaXplOiAxMnB4O1xuICBmb250LXdlaWdodDogNzAwO1xufVxuXG4ucG9saWN5LW1lc3NhZ2VzIHtcbiAgbGlzdC1zdHlsZTogZGlzYztcbiAgbWFyZ2luOiA2cHggMCAwO1xuICBwYWRkaW5nLWxlZnQ6IDI2cHg7XG4gIGNvbG9yOiAjN2Y4YzhkO1xuICBmb250LXNpemU6IDEycHg7XG59XG5cbi5wb2xpY3ktbWVzc2FnZXMgbGkge1xuICBtYXJnaW46IDJweCAwO1xuICB3b3JkLWJyZWFrOiBicmVhay13b3JkO1xufVxuIl0sInNvdXJjZVJvb3QiOiIifQ== */"]
    });
  }
}

/***/ }),

/***/ 1250:
/*!*******************************************!*\
  !*** ./src/app/config/keycloak.config.ts ***!
  \*******************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   "default": () => (__WEBPACK_DEFAULT_EXPORT__)
/* harmony export */ });
const keycloakConfig = {
  url: 'http://platform-auth.127.0.0.1.sslip.io',
  realm: 'teams',
  clientId: 'teams-ui'
};
/* harmony default export */ const __WEBPACK_DEFAULT_EXPORT__ = (keycloakConfig);

/***/ }),

/***/ 472:
/*!**************************************************!*\
  !*** ./src/app/interceptors/auth.interceptor.ts ***!
  \**************************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   AuthInterceptor: () => (/* binding */ AuthInterceptor)
/* harmony export */ });
/* harmony import */ var _angular_core__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @angular/core */ 7580);
/* harmony import */ var _services_auth_service__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../services/auth.service */ 4796);


class AuthInterceptor {
  constructor(authService) {
    this.authService = authService;
  }
  intercept(req, next) {
    // Add JWT token to API requests
    if (req.url.includes('/') && this.authService.isLoggedInSync()) {
      const token = this.authService.getTokenSync();
      if (token) {
        const authReq = req.clone({
          setHeaders: {
            Authorization: `Bearer ${token}`
          }
        });
        return next.handle(authReq);
      }
    }
    return next.handle(req);
  }
  static {
    this.ɵfac = function AuthInterceptor_Factory(t) {
      return new (t || AuthInterceptor)(_angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵinject"](_services_auth_service__WEBPACK_IMPORTED_MODULE_0__.AuthService));
    };
  }
  static {
    this.ɵprov = /*@__PURE__*/_angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵdefineInjectable"]({
      token: AuthInterceptor,
      factory: AuthInterceptor.ɵfac
    });
  }
}

/***/ }),

/***/ 4796:
/*!******************************************!*\
  !*** ./src/app/services/auth.service.ts ***!
  \******************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   AuthService: () => (/* binding */ AuthService)
/* harmony export */ });
/* harmony import */ var _Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./node_modules/@babel/runtime/helpers/esm/asyncToGenerator.js */ 9204);
/* harmony import */ var _angular_core__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @angular/core */ 7580);
/* harmony import */ var keycloak_angular__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! keycloak-angular */ 9837);



class AuthService {
  constructor(keycloak) {
    this.keycloak = keycloak;
    this._isLoggedIn = false;
    this._token = "";
    this.initializeAuth();
  }
  initializeAuth() {
    var _this = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        _this._isLoggedIn = yield _this.keycloak.isLoggedIn();
        if (_this._isLoggedIn) {
          // Ensure token is fresh
          yield _this.refreshTokenIfNeeded();
          _this._token = yield _this.keycloak.getToken();
        }
      } catch (error) {
        console.error("Failed to initialize auth state:", error);
        _this._isLoggedIn = false;
        _this._token = "";
      }
    })();
  }
  refreshTokenIfNeeded() {
    var _this2 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        // Check if token needs refresh (refresh if expires in next 30 seconds)
        const refreshed = yield _this2.keycloak.updateToken(30);
        if (refreshed) {
          console.log("🔄 Token refreshed");
          _this2._token = yield _this2.keycloak.getToken();
        } else {
          console.log("✅ Token is still valid");
        }
      } catch (error) {
        console.error("❌ Token refresh failed:", error);
        // Token refresh failed - user needs to login again
        _this2._isLoggedIn = false;
        _this2._token = "";
        throw error;
      }
    })();
  }
  isLoggedInSync() {
    return this._isLoggedIn;
  }
  isLoggedIn() {
    var _this3 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        _this3._isLoggedIn = yield _this3.keycloak.isLoggedIn();
        if (_this3._isLoggedIn) {
          yield _this3.refreshTokenIfNeeded();
        }
        return _this3._isLoggedIn;
      } catch (error) {
        console.error("Error checking login status:", error);
        return false;
      }
    })();
  }
  loadUserProfile() {
    var _this4 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        // Ensure we have a fresh token
        yield _this4.refreshTokenIfNeeded();
        return yield _this4.keycloak.loadUserProfile();
      } catch (error) {
        console.error("Failed to load user profile:", error);
        throw error;
      }
    })();
  }
  login() {
    var _this5 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      yield _this5.keycloak.login();
      yield _this5.initializeAuth();
    })();
  }
  logout() {
    var _this6 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      yield _this6.keycloak.logout();
      _this6._isLoggedIn = false;
      _this6._token = "";
    })();
  }
  getTokenSync() {
    return this._token;
  }
  getToken() {
    var _this7 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        yield _this7.refreshTokenIfNeeded();
        _this7._token = yield _this7.keycloak.getToken();
        return _this7._token;
      } catch (error) {
        console.error("Failed to get token:", error);
        return "";
      }
    })();
  }
  // ADD THIS METHOD to your src/app/services/auth.service.ts file
  getUserInfoFromToken() {
    try {
      const token = this.getTokenSync();
      if (!token) {
        console.log("🔍 Debug - No token available");
        return null;
      }
      // Decode JWT payload
      const payload = JSON.parse(atob(token.split(".")[1]));
      console.log("🔍 Debug - Token payload:", payload);
      return {
        username: payload.preferred_username,
        email: payload.email,
        firstName: payload.given_name,
        lastName: payload.family_name,
        name: payload.name,
        roles: payload.realm_access?.roles || []
      };
    } catch (error) {
      console.error("❌ Failed to decode token:", error);
      return null;
    }
  }
  hasRole(role) {
    try {
      return this.keycloak.isUserInRole(role);
    } catch {
      return false;
    }
  }
  getUserRoles() {
    try {
      return this.keycloak.getUserRoles();
    } catch {
      return [];
    }
  }
  refreshAuthState() {
    var _this8 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      yield _this8.initializeAuth();
    })();
  }
  // Debug method to check token validity
  debugTokenInfo() {
    var _this9 = this;
    return (0,_Users_rdutta_Development_platform_engineering_capstone_project_platform_idp_teams_management_teams_app_node_modules_babel_runtime_helpers_esm_asyncToGenerator_js__WEBPACK_IMPORTED_MODULE_0__["default"])(function* () {
      try {
        const token = yield _this9.getToken();
        if (!token) {
          return {
            error: "No token available"
          };
        }
        // Decode JWT payload (just for debugging - don't do this in production)
        const payload = JSON.parse(atob(token.split(".")[1]));
        const now = Math.floor(Date.now() / 1000);
        return {
          hasToken: !!token,
          tokenLength: token.length,
          expires: new Date(payload.exp * 1000),
          expiresInSeconds: payload.exp - now,
          isExpired: payload.exp < now,
          audience: payload.aud,
          subject: payload.sub,
          roles: payload.realm_access?.roles || []
        };
      } catch (error) {
        return {
          error: error
        };
      }
    })();
  }
  static {
    this.ɵfac = function AuthService_Factory(t) {
      return new (t || AuthService)(_angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵinject"](keycloak_angular__WEBPACK_IMPORTED_MODULE_2__.KeycloakService));
    };
  }
  static {
    this.ɵprov = /*@__PURE__*/_angular_core__WEBPACK_IMPORTED_MODULE_1__["ɵɵdefineInjectable"]({
      token: AuthService,
      factory: AuthService.ɵfac,
      providedIn: "root"
    });
  }
}

/***/ }),

/***/ 5092:
/*!*******************************************!*\
  !*** ./src/app/services/teams.service.ts ***!
  \*******************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   TeamsService: () => (/* binding */ TeamsService)
/* harmony export */ });
/* harmony import */ var rxjs__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! rxjs */ 7919);
/* harmony import */ var rxjs_operators__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! rxjs/operators */ 1318);
/* harmony import */ var _environments_environment__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../../environments/environment */ 5312);
/* harmony import */ var _angular_core__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! @angular/core */ 7580);
/* harmony import */ var _angular_common_http__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! @angular/common/http */ 6443);
/* harmony import */ var _auth_service__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./auth.service */ 4796);






class TeamsService {
  constructor(http, authService) {
    this.http = http;
    this.authService = authService;
    this.apiUrl = _environments_environment__WEBPACK_IMPORTED_MODULE_0__.environment.apiUrl;
    this.handleError = error => {
      let errorMessage = 'An error occurred';
      console.error('API Error:', error);
      if (error.status === 401) {
        errorMessage = 'Unauthorized. Please log in again.';
        this.authService.login();
      } else if (error.status === 403) {
        errorMessage = 'Forbidden. You don\'t have permission for this action.';
      } else if (error.error instanceof ErrorEvent) {
        // Client-side error
        errorMessage = error.error.message;
      } else {
        // Server-side error
        errorMessage = error.error?.detail || error.message || `HTTP ${error.status}`;
      }
      return (0,rxjs__WEBPACK_IMPORTED_MODULE_2__.throwError)(() => errorMessage);
    };
  }
  getTeams() {
    const url = `${this.apiUrl}/teams`;
    console.log('🔍 Making API call to:', url);
    console.log('🔐 User authenticated:', this.authService.isLoggedIn());
    return this.http.get(url).pipe((0,rxjs_operators__WEBPACK_IMPORTED_MODULE_3__.catchError)(this.handleError));
  }
  createTeam(team) {
    const url = `${this.apiUrl}/teams`;
    console.log('📝 Creating team via API:', url);
    return this.http.post(url, team).pipe((0,rxjs_operators__WEBPACK_IMPORTED_MODULE_3__.catchError)(this.handleError));
  }
  deleteTeam(teamId) {
    const url = `${this.apiUrl}/teams/${teamId}`;
    console.log('🗑️ Deleting team via API:', url);
    return this.http.delete(url).pipe((0,rxjs_operators__WEBPACK_IMPORTED_MODULE_3__.catchError)(this.handleError));
  }
  getComplianceSummaries() {
    const url = `${this.apiUrl}/compliance`;
    return this.http.get(url).pipe((0,rxjs_operators__WEBPACK_IMPORTED_MODULE_3__.catchError)(this.handleError));
  }
  getTeamCompliance(teamId) {
    const url = `${this.apiUrl}/teams/${teamId}/compliance`;
    return this.http.get(url).pipe((0,rxjs_operators__WEBPACK_IMPORTED_MODULE_3__.catchError)(this.handleError));
  }
  static {
    this.ɵfac = function TeamsService_Factory(t) {
      return new (t || TeamsService)(_angular_core__WEBPACK_IMPORTED_MODULE_4__["ɵɵinject"](_angular_common_http__WEBPACK_IMPORTED_MODULE_5__.HttpClient), _angular_core__WEBPACK_IMPORTED_MODULE_4__["ɵɵinject"](_auth_service__WEBPACK_IMPORTED_MODULE_1__.AuthService));
    };
  }
  static {
    this.ɵprov = /*@__PURE__*/_angular_core__WEBPACK_IMPORTED_MODULE_4__["ɵɵdefineInjectable"]({
      token: TeamsService,
      factory: TeamsService.ɵfac,
      providedIn: 'root'
    });
  }
}

/***/ }),

/***/ 5312:
/*!*****************************************!*\
  !*** ./src/environments/environment.ts ***!
  \*****************************************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony export */ __webpack_require__.d(__webpack_exports__, {
/* harmony export */   environment: () => (/* binding */ environment)
/* harmony export */ });
const environment = {
  production: false,
  // Use proxy path instead of direct URL or in coder use "http://<workspace-name>.coder:<port>" with the port of forward of the api service
  apiUrl: "http://teams-api.127.0.0.1.sslip.io",
  keycloak: {
    // same as above, but with keycloak forward port
    url: "http://platform-auth.127.0.0.1.sslip.io",
    realm: "teams",
    clientId: "teams-ui"
  }
};

/***/ }),

/***/ 4429:
/*!*********************!*\
  !*** ./src/main.ts ***!
  \*********************/
/***/ ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _angular_platform_browser__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @angular/platform-browser */ 436);
/* harmony import */ var _app_app_module__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./app/app.module */ 635);


_angular_platform_browser__WEBPACK_IMPORTED_MODULE_1__.platformBrowser().bootstrapModule(_app_app_module__WEBPACK_IMPORTED_MODULE_0__.AppModule).catch(err => console.error(err));

/***/ })

},
/******/ __webpack_require__ => { // webpackRuntimeModules
/******/ var __webpack_exec__ = (moduleId) => (__webpack_require__(__webpack_require__.s = moduleId))
/******/ __webpack_require__.O(0, ["vendor"], () => (__webpack_exec__(4429)));
/******/ var __webpack_exports__ = __webpack_require__.O();
/******/ }
]);
//# sourceMappingURL=main.js.map