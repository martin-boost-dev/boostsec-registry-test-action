# boostsec-registry-test-action

[![boostsecurity](https://api.boostsecurity.io/badges/6iuLhp-GUQuI2XQr/boostsecurityio/boostsec-registry-test-action)](https://api.boostsecurity.io/badges/6iuLhp-GUQuI2XQr/boostsecurityio/boostsec-registry-test-action/details)

Run test when a change is applied to the scanner-registry

# Development

If you wish to automatically run `make format lint` on commit, you can use [pre-commit](https://pre-commit.com/)
```
pre-commit install
```

- `make install`: Create or synchronize your virtualenv with the poetry.lock file
- `make update`: Run after any modification to the pyproject.toml.  Will update the poetry.lock and synchronizes your virtualenv.
- `make upgrade`: Pull new changes from the template repo and upgrade the dependencies
- `make format`: Auto-format your code
- `make lint`: Run linters
- `make test`: Run all tests, provides a coverage report

## Tips

### Adding a new dependency

- To add a runtime dependency: `poetry add <dependency>`
- To add a testing dependency: `poetry add <dependency> --group dev`
- Or, simply edit the pyproject.toml and run `make update`

Is the dependency required for consumers to use your .../testing module?

- Add the dependency to the runtime dependencies in this format
  ```
  docker = { version = "^5.0.3", optional = true }
  ```
- Add the optional dependency to the `testing` extras
  ```
  [tool.poetry.extras]
  testing = [
      "docker",
  ]
  ```
- Run `make update` to lock and update your virtualenv
