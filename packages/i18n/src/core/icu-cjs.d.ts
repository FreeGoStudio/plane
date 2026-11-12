// The dependency's CJS entry ships the root module declaration instead of a subpath declaration.
declare module "i18next-icu/cjs" {
  import ICU from "i18next-icu";
  export default ICU;
}
