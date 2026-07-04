new_dataset = []
total = 0
mutants = []
inital_content = []
with open("dataset.ttl", "r", encoding="utf-8") as file:
    lines = file.readlines()
    inital_content = lines[0:3]
    i = 3
    mutant = []
    while i < len(lines):
        if "<mb:mutant#" in lines[i]:
            id = lines[i].split("#")[1].split(">")[0]
            mutant.append(lines[i])
            i += 1
            while i < len(lines) and "<mb:mutant#" not in lines[i]:
                mutant.append(lines[i])
                i += 1
            mutants.append([id, mutant])
            mutant = []
sorted_dataset = [line for line in inital_content]
mutants.sort(key=lambda x: x[0])

for _, mutant in mutants:
    for line in mutant:
        sorted_dataset.append(line)

# Open the file in write mode ("w" will overwrite the existing file)
with open("sorted_dataset.ttl", "w", encoding="utf-8") as file:
    file.writelines(sorted_dataset)

print(f"Successfully sorted and saved {len(mutants)} mutants to sorted_dataset.ttl!")

