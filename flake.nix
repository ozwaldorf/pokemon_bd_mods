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
      devkitpro = pkgs.callPackage ./nix/devkitpro.nix { };
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
          pkgs.python312
          pkgs.uv
          pkgs.pkgsCross.aarch64-multiplatform.buildPackages.binutils
        ];

        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ];
        UV_PYTHON = "${pkgs.python312}/bin/python3.12";
        DEVKITPRO = "${devkitpro}";
        DEVKITA64 = "${devkitpro}/devkitA64";
      };
    };
}
