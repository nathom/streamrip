{
  description = "Application packaged using poetry2nix";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  #rip will complain it can't write to ~/.config because it's immutable. Seeing as there's no home manager module for this yet, I'd just make a config.toml somwhere and chmod 664 it. 
  outputs = { self, nixpkgs, flake-utils, poetry2nix }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        inherit (poetry2nix.lib.mkPoetry2Nix { inherit pkgs; }) mkPoetryApplication overrides;
      in
      {
        packages = {
          myapp = mkPoetryApplication { 
            projectDir = self; 
            preferWheels = true; #you can disable if you don't want yourself vulnerable to supply-side attacks but I'm not compiling all that
            overrides = 
              overrides.withDefaults (self: super:{
                windows-curses = null; #poetry2nix doesn't support flags yet, so we have to manually make this null
              });
            meta.mainProgram = "rip";
          };
          default = self.packages.${system}.myapp;
        };

        devShells.default = pkgs.mkShell {
          inputsFrom = [ self.packages.${system}.myapp ];
          packages = [ pkgs.poetry ];
        };
      });
}
