{
  description = "Shared Pokémon Brilliant Diamond mod development shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.il2cppdumper-src = {
    url = "github:Perfare/Il2CppDumper/4741d46ba9cd6159c5d853eb9d6fc48b4bfa2b1a";
    flake = false;
  };
  inputs.libhac-src = {
    url = "git+https://gitlab.com/ryujinx-classic/LibHac.git?rev=880bd34b784e0f2b964e016d1174d901b2048626";
    flake = false;
  };

  outputs = { nixpkgs, il2cppdumper-src, libhac-src, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      pythonEnv =
        let
          python = pkgs.python312;
          # Keep the existing lock as the source of truth for all Python versions and
          # download hashes. The development shell targets x86_64 Linux / Python 3.12.
          lock = builtins.fromTOML (builtins.readFile ./uv.lock);
          lockedPackages = builtins.filter (p: p.source ? registry) lock.package;
          compatibleWheel = wheel:
            let url = wheel.url; in
            pkgs.lib.hasSuffix "-py3-none-any.whl" url
            || (pkgs.lib.hasInfix "manylinux" url
              && pkgs.lib.hasInfix "x86_64" url
              && (pkgs.lib.hasInfix "-cp312-cp312-" url
                || pkgs.lib.hasInfix "-cp37-abi3-" url
                || pkgs.lib.hasInfix "-cp311-abi3-" url));
          packages = builtins.listToAttrs (map (package:
            let
              wheels = builtins.filter compatibleWheel (package.wheels or [ ]);
              useWheel = wheels != [ ];
              archive = if useWheel then builtins.head wheels else package.sdist;
            in {
              name = package.name;
              value = python.pkgs.buildPythonPackage {
                pname = package.name;
                inherit (package) version;
                format = if useWheel then "wheel" else "pyproject";
                src = pkgs.fetchurl {
                  inherit (archive) url;
                  sha256 = pkgs.lib.removePrefix "sha256:" archive.hash;
                };
                nativeBuildInputs = pkgs.lib.optional useWheel pkgs.autoPatchelfHook;
                buildInputs = [ pkgs.stdenv.cc.cc.lib pkgs.zlib ];
                build-system = pkgs.lib.optionals (!useWheel) [ python.pkgs.setuptools ];
                dependencies = map (dependency: packages.${dependency.name})
                  (package.dependencies or [ ]);
                doCheck = false;
              };
            }) lockedPackages);
          project = builtins.head (builtins.filter (p: p.source ? virtual) lock.package);
        in python.withPackages (_: map (dependency: packages.${dependency.name}) project.dependencies);
      devkitpro =
        let
          # Official devkitPro packages, matching the previously used build toolchain.
          package = directory: name: hash: pkgs.fetchurl {
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
        in pkgs.stdenvNoCC.mkDerivation {
          pname = "devkitpro-switch";
          version = "r29.2";
          dontUnpack = true;
          dontConfigure = true;
          dontBuild = true;
          dontStrip = true;
          dontAutoPatchelf = true;
          nativeBuildInputs = [ pkgs.autoPatchelfHook pkgs.zstd ];
          buildInputs = [ pkgs.stdenv.cc.cc.lib pkgs.zlib pkgs.expat ];

          installPhase = ''
            runHook preInstall
            mkdir -p packages "$out"
            for archive in ${pkgs.lib.escapeShellArgs (map toString archives)}; do
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
        };
      fetchNupkg = pkgs.callPackage
        "${nixpkgs}/pkgs/build-support/dotnet/fetch-nupkg" {
          inherit (pkgs.dotnetCorePackages) nugetPackageHook patchNupkgs;
        };
      il2cppdumper = pkgs.buildDotnetModule {
        pname = "il2cppdumper";
        version = "2024-07-06";
        src = il2cppdumper-src;
        projectFile = "Il2CppDumper/Il2CppDumper.csproj";
        nugetDeps = [
          (fetchNupkg {
            pname = "Mono.Cecil";
            version = "0.11.4";
            hash = "sha256-HrnRgFsOzfqAWw0fUxi/vkzZd8dMn5zueUeLQWA9qvs=";
          })
        ];
        dotnet-sdk = pkgs.dotnetCorePackages.sdk_8_0;
        dotnet-runtime = pkgs.dotnetCorePackages.runtime_8_0;
        executables = [ "Il2CppDumper" ];

        postPatch = ''
          substituteInPlace Il2CppDumper/Il2CppDumper.csproj \
            --replace-fail '<TargetFrameworks>net6.0;net8.0</TargetFrameworks>' \
                           '<TargetFramework>net8.0</TargetFramework>'
        '';
      };
      hactoolnet = pkgs.buildDotnetModule {
        pname = "hactoolnet";
        version = "0.20.0-unstable-2026-05-28";
        src = libhac-src;
        projectFile = "src/hactoolnet/hactoolnet.csproj";
        nugetDeps = [ ];
        dotnet-sdk = pkgs.dotnetCorePackages.sdk_10_0;
        dotnet-runtime = pkgs.dotnetCorePackages.runtime_10_0;
        executables = [ "hactoolnet" ];
      };
    in {
      packages.${system} = {
        inherit devkitpro hactoolnet il2cppdumper;
        python-env = pythonEnv;
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = [
          pkgs.android-tools
          pkgs.ffmpeg
          pkgs.hactool
          hactoolnet
          il2cppdumper
          pkgs.just
          pkgs.cmake
          pkgs.gnumake
          pkgs.gcc
          pkgs.git
          devkitpro
          pythonEnv
          pkgs.pkgsCross.aarch64-multiplatform.buildPackages.binutils
        ];

        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ];
        # Other tools bring their own Python interpreters. Prefer the project
        # environment for both interactive commands and the just recipes.
        shellHook = ''
          export PATH="${pythonEnv}/bin:$PATH"
        '';
        DEVKITPRO = "${devkitpro}";
        DEVKITA64 = "${devkitpro}/devkitA64";
      };
    };
}
