.PHONY: baml-generate baml-format baml-test help

help:
	@echo "Available targets:"
	@echo "  baml-generate  Regenerate baml_client/ from baml_src/*.baml"
	@echo "  baml-format    Format baml_src/*.baml in place"
	@echo "  baml-test      Run BAML prompt tests"

baml-generate:
	baml-cli generate --from baml_src

baml-format:
	baml-cli fmt --from baml_src

baml-test:
	baml-cli test --from baml_src
