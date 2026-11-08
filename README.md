# StringArt
Project for algorithmics course 2020. Also submitted to DeltaX 2021. Recreate art by connecting nails with strings.

For a quick overview of the project, look at the project's [poster](https://raw.githubusercontent.com/kaspar98/StringArt/main/docs/Algoritmika%20poster%20puhtand.pdf).

**Project goal**<br>
Recreate images by looping a continuous string around nails. The nails are fixed on the border of a canvas (e.g. on a circle’s or rectangle’s perimeter).

**Project result**<br>
A software tool that can be used from the command line to create string art and get instructions to replicate the result.

**Core of the project**<br>
Input: nail positions, reference image.<br>
Output: a string art version of the reference image; and the order of nails around which to loop the continuous string to get the output image. 

The algorithm:<br>
1) Evaluate the goodness of every possible string pull from the current nail.*¹ <br>
2) Pull the string to the best found nail. <br>
3) Set the new nail as the current nail. <br>
4) Repeat the algorithm.*²<br>

*¹ To evaluate the goodness of a string pull, evaluate pixel by pixel, how much better or worse does the pull make the picture. Distance of two pixels is the square difference. The best line is the one with most cumulative improvement.<br>
*² The number of iterations can be set manually or the algorithm can be set to repeat until it fails to find string pulls that improve the total result.<br>

# Project structure
Standard Python [src-layout](https://packaging.python.org/en/latest/tutorials/packaging-projects/) managed with [uv](https://docs.astral.sh/uv/):

```
├── pyproject.toml       # PEP 621 metadata, dependencies, tool configs
├── src/string_art/      # the installable package
│   ├── cli.py           # command line interface (entry point)
│   ├── generator.py     # greedy algorithm and B/W + RGB pipelines
│   ├── nails.py         # nail position creation and scaling
│   ├── canvas.py        # canvas init and thread drawing
│   └── image_transformations.py  # rgb2gray, largest_square
├── tests/               # pytest suite
├── notebooks/           # original research notebooks
├── examples/            # example outputs
└── docs/                # project poster
```

# Installation
Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) (it manages the Python 3.11+ interpreter itself):

```bash
uv sync
```

# Run from cmd
```bash
uv run string-art -i <input.png> -o <output.png>
```

The same via module invocation:

```bash
uv run python -m string_art -i <input.png> -o <output.png>
```

Possible flags:
* “-i <path>” input image;
* “-o <path>” output file (default is output.png);
* “-d <int>” output file dimensions (default is 300); if output dimens are scaled up, then string strength should also be;<br>
* “-l <int>” number of iterations (default will run until no improvement);<br>
* “-r <int>” number of random nails to pick from when choosing the next nail to speed up the algorithm at the cost of quality (default looks at all possible nails every iteration; good value for this is ~50);<br>
* “-r1 <float>” vertical radius multiplier for the nail ellipse (default is 1, i.e. a circle);<br>
* “-r2 <float>” horizontal radius multiplier for the nail ellipse (default is 1, i.e. a circle);<br>
* “-n <int>” step between nails (default is 4). The smaller the step, the more nails there will be. The larger the step, the less nails. Minimum possible value is 1;<br>
* “-s <float 0..1>” string strength for output (default is 0.1);<br>
* “--rgb” for colored output (default is black string on white canvas). In case of RGB, pull order isn't returned as it might not match the real life result (additive blending);<br>
* “--wb” for white string on a black canvas;<br>
* “--rect” to put nails in a square around the picture (default is circle).<br>

Nails are placed evenly around the perimeter. For circles the first nail is placed at 9 o'clock and the order goes clockwise. For squares, the first nail is placed at the top left corner and the order goes clockwise.

# Development
```bash
uv run pytest          # run the test suite
uv run ruff check .    # lint
```

The research notebooks in `notebooks/` import the package (`from string_art.image_transformations import *`), so run `uv sync` first.

# Examples
![Ex1](https://raw.githubusercontent.com/kaspar98/StringArt/main/examples/Algoritmika%20fig%201.png)
--------
![Ex2](https://raw.githubusercontent.com/kaspar98/StringArt/main/examples/Algoritmika%20projekt%20fig%202.png)
--------
![Ex3](https://raw.githubusercontent.com/kaspar98/StringArt/main/examples/Algoritmika%20fig%203.png)
--------
![Ex4](https://raw.githubusercontent.com/kaspar98/StringArt/main/examples/Algoritmika%20fig%204.png)
