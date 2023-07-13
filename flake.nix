{
  description = "Flake to create kraken wrapper application";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, poetry2nix, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        overlays = [ poetry2nix.overlay ];
        pkgs = import nixpkgs {
          inherit system overlays;
        };
        krakenwRaw = pkgs.poetry2nix.mkPoetryApplication {
          projectDir = ./kraken-wrapper;
          preferWheels = true;
        };
        krakenw = pkgs.writeShellScriptBin "krakenw" ''
          # This is a hack! For Cargo proxying, Kraken depends on mitmproxy. Indirectly, mitmproxy as compiled for Linux relies
          # on being able to use libstdc++, but because it is executed as a subprocess, it's not able to be found in a Nix Linux
          # environment. For now, we can add libstdc++ to the LD_LIBRARY_PATH to ensure that it's linked correctly. At the same
          # time, we also replace the Python for Kraken to use. While this limits the user to Python3.10, this should remain
          # compatible for the foreseeable future.
          export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:${pkgs.stdenv.cc.cc.lib}/lib"
          export PATH="${pkgs.python310}/bin:$PATH"
          exec ${krakenwRaw}/bin/krakenw $@
        '';
      in
      rec {
        packages = flake-utils.lib.flattenTree rec {
          inherit krakenw;
          default = krakenw;
        };
      }
    );
}
