# Build .skill bundles on demand.
#
#   make                          package every skill that changed
#   make clear-prose              package one skill by name
#   make dist/clear-prose.skill   same thing, by path
#   make validate                 check skills + marketplace wiring
#   make test                     run the hook tests
#   make list                     show skills and the plugin each belongs to
#   make clean                    remove dist/
#
# Skills live at plugins/<plugin>/skills/<skill>/SKILL.md. Bundles are named
# after the skill, not the plugin, so skill names must be unique repo-wide;
# `make validate` fails on a collision.
#
# Targets rebuild only when a file inside the skill directory is newer than the
# bundle, so `make` twice in a row does nothing the second time.

SKILL_DIRS  := $(patsubst %/SKILL.md,%,$(wildcard plugins/*/skills/*/SKILL.md))
SKILL_NAMES := $(notdir $(SKILL_DIRS))
BUNDLES     := $(addprefix dist/,$(addsuffix .skill,$(SKILL_NAMES)))

# The scripts declare their dependencies inline (PEP 723), which uv reads. Without
# uv, fall back to python3; the README lists what to pip install for that.
PYTHON := $(if $(shell command -v uv),uv run --quiet --script,python3)

.PHONY: all validate test list clean $(SKILL_NAMES)
.DEFAULT_GOAL := all

all: $(BUNDLES)

# One rule per skill, so each bundle depends on its own source directory.
# $(1) is the skill directory; $(notdir $(1)) is the skill name.
define SKILL_RULE
dist/$(notdir $(1)).skill: $(shell find $(1) -type f -not -name '.DS_Store') build.py
	@$(PYTHON) build.py package $(notdir $(1))

$(notdir $(1)): dist/$(notdir $(1)).skill
endef

$(foreach d,$(SKILL_DIRS),$(eval $(call SKILL_RULE,$(d))))

validate:
	@$(PYTHON) build.py validate

test:
	@$(PYTHON) tests/test_prose_check.py

list:
	@$(PYTHON) build.py list

clean:
	@$(PYTHON) build.py clean
