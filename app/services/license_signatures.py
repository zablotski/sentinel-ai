"""Canonical license text excerpts used to classify UNKNOWN licenses.

Each entry maps an SPDX identifier to a distinctive excerpt of the license
text. Excerpts are intentionally short: the classifier matches on the
preamble/operative wording, which differs strongly between families.
"""

LICENSE_SIGNATURES: dict[str, str] = {
    "MIT": (
        "Permission is hereby granted, free of charge, to any person obtaining a copy "
        "of this software and associated documentation files (the \"Software\"), to deal "
        "in the Software without restriction, including without limitation the rights to "
        "use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of "
        "the Software, and to permit persons to whom the Software is furnished to do so, "
        "subject to the following conditions: The above copyright notice and this "
        "permission notice shall be included in all copies or substantial portions of the "
        "Software."
    ),
    "Apache-2.0": (
        "License, Version 2.0, January 2004. TERMS AND CONDITIONS FOR USE, REPRODUCTION, "
        "AND DISTRIBUTION. Definitions: \"License\" shall mean the terms and conditions "
        "for use, reproduction, and distribution. \"Licensor\" shall mean the copyright "
        "owner. \"You\" (or \"Your\") shall mean an individual or Legal Entity exercising "
        "permissions granted by this License. Grant of Copyright License: subject to the "
        "terms and conditions of this License, each Contributor hereby grants to You a "
        "perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable "
        "copyright license to reproduce, prepare Derivative Works of, publicly display, "
        "sublicense, and distribute the Work."
    ),
    "BSD-3-Clause": (
        "Redistribution and use in source and binary forms, with or without modification, "
        "are permitted provided that the following conditions are met: Redistributions of "
        "source code must retain the above copyright notice, this list of conditions and "
        "the following disclaimer. Redistributions in binary form must reproduce the above "
        "copyright notice, this list of conditions and the following disclaimer in the "
        "documentation and/or other materials provided with the distribution. Neither the "
        "name of the copyright holder nor the names of its contributors may be used to "
        "endorse or promote products derived from this software."
    ),
    "BSD-2-Clause": (
        "Redistribution and use in source and binary forms, with or without modification, "
        "are permitted provided that the following conditions are met: Redistributions of "
        "source code must retain the above copyright notice, this list of conditions and "
        "the following disclaimer. Redistributions in binary form must reproduce the above "
        "copyright notice, this list of conditions and the following disclaimer in the "
        "documentation and/or other materials provided with the distribution."
    ),
    "ISC": (
        "Permission to use, copy, modify, and/or distribute this software for any purpose "
        "with or without fee is hereby granted, provided that the above copyright notice "
        "and this permission notice appear in all copies."
    ),
    "GPL-2.0-only": (
        "GNU GENERAL PUBLIC LICENSE Version 2, June 1991. Preamble: The licenses for most "
        "software are designed to take away your freedom to share and change it. By "
        "contrast, the GNU General Public License is intended to guarantee your freedom to "
        "share and change all versions of a program. We protect your rights with two steps: "
        "(1) assert copyright on the software, and (2) offer you this License which gives "
        "you legal permission to copy, distribute and/or modify it. These terms are "
        "imposed to protect your rights."
    ),
    "GPL-3.0-only": (
        "GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007. Preamble: The GNU General "
        "Public License is a free, copyleft license for software and other kinds of works. "
        "The licenses for most software and other practical works are designed to take "
        "away your freedom to share and change the works. To protect your rights, we need "
        "to prevent others from denying you these rights or asking you to surrender the "
        "rights. Corresponding Source means the entire work of authorship."
    ),
    "AGPL-3.0-only": (
        "GNU AFFERO GENERAL PUBLIC LICENSE Version 3, 19 November 2007. Preamble: The GNU "
        "Affero General Public License is a free, copyleft license for software and other "
        "kinds of works, specifically designed to ensure cooperation with the community "
        "in the case of network server software. Unlike most general public licenses, our "
        "General Public Licenses are designed for software that runs over computer "
        "networks: you offering users interaction through a network must provide them "
        "Corresponding Source."
    ),
    "LGPL-2.1-only": (
        "GNU LESSER GENERAL PUBLIC LICENSE Version 2.1, February 1999. Preamble: The "
        "licenses for most software are designed to take away your freedom to share and "
        "change it. The GNU General Public Licenses are designed to guarantee your "
        "freedom. This License, the Lesser General Public License, stems from the GNU "
        "General Public License but permits linking under less restrictive terms for "
        "libraries."
    ),
    "LGPL-3.0-only": (
        "GNU LESSER GENERAL PUBLIC LICENSE Version 3, 29 June 2007. This version of the "
        "GNU Lesser General Public License incorporates the terms and conditions of "
        "version 3 of the GNU General Public License, supplemented by additional "
        "permissions for linking under this License."
    ),
    "MPL-2.0": (
        "Mozilla Public License Version 2.0. 1. Definitions. \"Contributor\" means each "
        "individual or legal entity that creates, contributes to the creation of, or owns "
        "Covered Software. \"Larger Work\" means a work that combines Covered Software "
        "with other material. If You include Covered Source Code in a larger work, the "
        "larger work may be governed by the terms of Your choice, provided You remain in "
        "compliance with this License for the Covered Software."
    ),
    "Unlicense": (
        "This is free and unencumbered software released into the public domain. Anyone "
        "is free to copy, modify, publish, use, compile, sell, or distribute this "
        "software, either in source code form or as a compiled binary, for any purpose, "
        "commercial or non-commercial, and by any means."
    ),
    "Zlib": (
        "This software is provided 'as-is', without any express or implied warranty. In "
        "no event will the authors be held liable for any damages arising from the use of "
        "this software. Permission is granted to anyone to use this software for any "
        "purpose, including commercial applications, and to alter it and redistribute it "
        "freely, subject to restrictions."
    ),
    "0BSD": (
        "Permission to use, copy, modify, and/or distribute this software for any purpose "
        "with or without fee is hereby granted. THE SOFTWARE IS PROVIDED \"AS IS\" AND THE "
        "AUTHOR DISCLAIMS ALL WARRANTIES."
    ),
}
