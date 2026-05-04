import type { AppProps } from "next/app";

import "../src/styles/globals.css";

export default function SyncoreApp({ Component, pageProps }: AppProps) {
  return <Component {...pageProps} />;
}
