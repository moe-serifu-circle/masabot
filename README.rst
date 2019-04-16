MasaBot
=======
An automated discord bot for handling typical tasks.

Dev Setup
---------
Masabot requires python 3. If you don't have it, install it.

To install `masabot`, first clone the repo to the local system::

    git clone git@github.com:moe-serifu-circle/masabot.git

Masabot is currently a long-running foreground process; to prevent accidental disconnection ighly-recommended

Masabot has a `setup.py`, so that can be used to install all library dependencies, but this should be done in a virtual
environment. Set up one somewhere; this one uses masabot's home directory, and creates it in a directory that is ignored
by git::

    cd masabot
    python3 -m venv .venv

Then, to enter the virtual environment (which should always be done to avoid polluting the global python namespace), you
run the activation script.

On Windows, this is::

    .venv\Scripts\activate.bat

On Mac/Unix/Linux, this is::

    . .venv/bin/activate

Now the environment is prepared, but before launching masabot, its Configuration_ must be set up. Copy the
`config-example.json` file to `config.json`, and fill in the values approriately. At minimum, the `discord-api-key` must
be set to the token for your bot, and the masters list should contain at least one user's uuid. For information on
obtaining a bot token, see `Obtaining a Discord Key`_ in the Configuration_ section; for information on master users,
see `Masters List`_ in the Configuration_ section.

Once `masabot` is fully configured, it can be started via its supervisor. To launch the masabot supervisor, execute the
`run-masabot.sh` script::

    ./run-masabot.sh

Assuming everything is configured properly, MasaBot will now be started and running on the servers she has been invited
to.

animelist Module: Additional Setup
..................................

Anilist
~~~~~~~
First, go to anilist at  https://anilist.co/settings/developer and create a new
API v2 client. Set the name to anything you want, but be sure to set the
redirect URI to something on your system.

Then, copy the secret and client ID to your config.json file.


Environment Variables
---------------------
Some environment variables may be used to override settings in the ``config.json`` file. If present, the value
of the environment variable takes precedence over any that are defined in config.

The following environment variables are recognized:

* ``MASABOT_DISCORD_API_KEY`` corresponds to ``"discord-api-key"`` in the config file.

* ``MASABOT_ANIMELIST__ANILIST_CLIENT_ID`` corresponds to ``"animelist"."anilist-client-id"`` in the config file.

* ``MASABOT_ANIMELIST__ANILIST_CLIENT_SECRET`` corresponds to ``"animelist"."anilist-client-secret"`` in the config
  file.

* ``MASABOT_ANNOUNCE_CHANNELS`` corresponds to ``"announce-channels"`` in the config file. This variable contains the
  name of each room to announce in, separated by commas.


Integration Tests
-----------------
To execute integration tests, go to the project root directory and then type in `./run-int-tests.sh`.
