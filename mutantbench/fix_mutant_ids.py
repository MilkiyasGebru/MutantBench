import hashlib
import rdflib


def sha1sum(content):
    sha1 = hashlib.sha1()
    sha1.update(content.encode('utf-8'))
    return sha1.hexdigest()


# Tracks mismatched id to the actual correct id
changes = {}
g = rdflib.Graph()
g.parse("dataset.ttl", format="turtle")

MB = rdflib.Namespace(
    "https://b2share.eudat.eu/records/153db16ce2f6401298a9aea8b0ab9781/"
)
total_mutants = 0
mismatched_ids = 0
unique_ids  = set()
for mutant in g.subjects(rdflib.RDF.type, MB.Mutant):
    diff = g.value(mutant, MB.difference)
    program = g.value(mutant, MB.program)

    program_name = str(program).split("#")[-1]

    _, mutant_id = mutant.split("#")
    mutant_id = mutant_id.strip()

    diff = "\n".join([x.strip() for x in diff.split("\n")])
    calculated_mutant_id = sha1sum(program_name + diff)
    if mutant_id != calculated_mutant_id:
        changes[mutant_id] = calculated_mutant_id
        mismatched_ids += 1
    if mutant_id == calculated_mutant_id:
        unique_ids.add(mutant_id)

    total_mutants += 1
print("Total mutants is ", total_mutants)
print("Total mismatch is", mismatched_ids)

new_dataset = []
total = 0
with open("dataset.ttl", "r", encoding="utf-8") as file:
    for line in file:
        if "<mb:mutant#" in line:
            total += 1
            for key in changes.keys():
                if key in line:
                    line = line.replace(key, changes[key])
                    break
        new_dataset.append(line)

with open("dataset.ttl", "w", encoding="utf-8") as outfile:
    outfile.writelines(new_dataset)
