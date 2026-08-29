import { useParams } from "react-router-dom";
import { NotFound } from "./NotFound";
import { CharactersPage } from "../features/characters/CharactersPage";

export function CharactersRoute() {
  const { characterId } = useParams();
  if (characterId !== undefined && !/^[1-9]\d*$/.test(characterId)) {
    return <NotFound message="The character route ID must be a positive integer." />;
  }
  return <CharactersPage />;
}
