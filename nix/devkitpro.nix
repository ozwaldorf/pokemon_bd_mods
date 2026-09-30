{ lib, stdenvNoCC, fetchurl, autoPatchelfHook, stdenv, zstd, zlib, expat }:

let
  # Official devkitPro packages, matching the previously used build toolchain.
  package = directory: name: hash: fetchurl {
    url = "https://pkg.devkitpro.org/packages/${directory}${name}.pkg.tar.zst";
    sha256 = hash;
    curlOptsList = [ "--user-agent" "devkitPro pacman/6.0.2" ];
  };
  archives = [
    (package "linux/x86_64/" "devkita64-binutils-2.45.1-2-x86_64" "4349c8e64381818c0da8d8d633ce0b0e809a6e07c1a0aa575468c8d0c10852a9")
    (package "linux/x86_64/" "devkita64-gcc-15.2.0-7-x86_64" "7a791f22db17d9085232c95926020c2a551fe29cd107b0a193aac65608fd3c1a")
    (package "" "devkita64-newlib-4.6.0.20260123-4-any" "fc97ba1009a94b68f8714c3cc548ef697ca82687b72fe0c05a7ca3df81beb53e")
    (package "" "devkita64-rules-1.1.1-1-any" "2649cf7827243447070073acc2aa2fee152a0592fc30e827ceed803c565a1ede")
    (package "" "libnx-4.12.0-1-any" "c6950bdf8e4b872ece492225368c03e633776329548a7494f91aa1e8f239cd8a")
    (package "linux/x86_64/" "switch-tools-1.13.1-1-x86_64" "de0a9473764d3c5205a7cc9b640e9e913c371b5684d526133384eb7e545c7dab")
    (package "linux/x86_64/" "general-tools-1.4.4-1-x86_64" "b6b59bd3d22d4f83a7f0668f749df7cf97b1f05083031e629d43ca4f4377c7b5")
  ];
in stdenvNoCC.mkDerivation {
  pname = "devkitpro-switch";
  version = "r29.2";
  dontUnpack = true;
  dontConfigure = true;
  dontBuild = true;
  dontStrip = true;
  dontAutoPatchelf = true;
  nativeBuildInputs = [ autoPatchelfHook zstd ];
  buildInputs = [ stdenv.cc.cc.lib zlib expat ];

  installPhase = ''
    runHook preInstall
    mkdir -p packages "$out"
    for archive in ${lib.escapeShellArgs (map toString archives)}; do
      tar -xf "$archive" -C packages
    done
    cp -a packages/opt/devkitpro/. "$out/"
    # Patch host executables only; the AArch64 libraries must remain untouched.
    autoPatchelf "$out/devkitA64/bin" "$out/devkitA64/libexec" "$out/tools/bin"
    runHook postInstall
  '';

  meta = {
    description = "Pinned devkitA64, libnx, and Switch packaging tools";
    homepage = "https://devkitpro.org/";
    platforms = [ "x86_64-linux" ];
  };
}
