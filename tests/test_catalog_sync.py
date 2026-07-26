from app.services.catalog_sync import flatten_chain


def test_flattens_branching_chain_by_depth_then_stable_species_id() -> None:
    chain = {
        "species": {
            "name": "root",
            "url": "https://pokeapi.co/api/v2/pokemon-species/1/",
        },
        "evolves_to": [
            {
                "species": {
                    "name": "branch-b",
                    "url": "https://pokeapi.co/api/v2/pokemon-species/20/",
                },
                "evolves_to": [],
            },
            {
                "species": {
                    "name": "branch-a",
                    "url": "https://pokeapi.co/api/v2/pokemon-species/10/",
                },
                "evolves_to": [
                    {
                        "species": {
                            "name": "leaf",
                            "url": "https://pokeapi.co/api/v2/pokemon-species/30/",
                        },
                        "evolves_to": [],
                    }
                ],
            },
        ],
    }
    flattened = flatten_chain(chain)
    assert [item.name for item in flattened] == [
        "root",
        "branch-a",
        "branch-b",
        "leaf",
    ]
    assert [item.depth for item in flattened] == [0, 1, 1, 2]

