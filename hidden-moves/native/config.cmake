set(LOGGER_IP 127.0.0.1)
set(LOGGER_PORT 3080)
add_module(9 HiddenMoves
    INCLUDE include/nn include/game include src/common
    SOURCE src/common/exlaunch src/mod)
set_property(TARGET HiddenMoves PROPERTY EMBED_BINARIES "")
add_module_variant(HiddenMoves Diamond 0100000011D90000 "Pokemon Brilliant Diamond")
